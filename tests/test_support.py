import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from fastapi.testclient import TestClient
from openai.types.chat import ChatCompletion

from sample_agent.agent import AzureAgent, INSTRUCTIONS, open_agent
from sample_agent.app import app
from sample_agent.knowledge import get_service_status, search_knowledge


class KnowledgeTests(unittest.TestCase):
    def test_search_normalizes_accents_and_case(self):
        self.assertEqual(search_knowledge("CONTRASEÑA")[0]["id"], "KB-003")

    def test_search_has_no_unrelated_matches(self):
        self.assertEqual(search_knowledge("¿Cuál es el clima?"), [])
        self.assertEqual(search_knowledge(""), [])

    def test_search_can_return_multiple_sources(self):
        self.assertEqual(len(search_knowledge("VPN, correo y MFA")), 3)

    def test_unknown_service_is_not_reported_healthy(self):
        self.assertIn("desconocido", get_service_status("otro"))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"AGENT_MODE": "demo"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = self.enterContext(TestClient(app))

    def test_health_exposes_mode(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok", "mode": "demo"})

    def test_vpn_demo_includes_evidence_and_incident(self):
        response = self.client.post("/chat", json={"message": "No conecta mi VPN"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "demo")
        for expected in ("SIMULACIÓN sin LLM", "KB-001", "INC-DEMO-001"):
            self.assertIn(expected, body["answer"])

    def test_mfa_demo_does_not_request_secrets(self):
        answer = self.client.post("/chat", json={"message": "Perdí mi MFA"}).json()["answer"]
        self.assertIn("KB-003", answer)
        self.assertIn("Nunca compartas", answer)

    def test_missing_evidence_escalates(self):
        answer = self.client.post("/chat", json={"message": "Escribe una novela"}).json()["answer"]
        self.assertIn("No hay evidencia", answer)
        self.assertIn("soporte humano", answer)

    def test_invalid_messages(self):
        for payload in (
            {}, {"message": ""}, {"message": "  "}, {"message": "a" * 2001},
            {"message": 123}, {"message": "VPN", "session_id": "otra-persona"},
        ):
            with self.subTest(payload_type=str(type(payload.get("message")))):
                self.assertEqual(self.client.post("/chat", json=payload).status_code, 422)

    def test_failure_does_not_leak_provider_details(self):
        app.state.agent = AsyncMock()
        app.state.agent.answer.side_effect = RuntimeError("private-provider-details")
        response = self.client.post("/chat", json={"message": "VPN"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-provider-details", response.text)

    def test_timeout_returns_gateway_timeout(self):
        app.state.agent = AsyncMock()
        app.state.agent.answer.side_effect = TimeoutError
        self.assertEqual(
            self.client.post("/chat", json={"message": "VPN"}).status_code, 504
        )


class AzureTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_mode_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "AGENT_MODE"):
            async with open_agent("azuer"):
                self.fail("No debe aceptar un modo inválido")

    async def test_azure_requires_valid_configuration(self):
        for endpoint, deployment in (
            ("", ""), ("http://example.com", "chat"),
            ("https://example.com/openai/v1", "chat"),
            ("https://example.com?key=value", "chat"),
            ("https://example.com", ""),
        ):
            with self.subTest(endpoint=endpoint), patch.dict(os.environ, {
                "AZURE_OPENAI_ENDPOINT": endpoint,
                "AZURE_OPENAI_DEPLOYMENT": deployment,
            }, clear=True):
                with self.assertRaisesRegex(ValueError, "AZURE_OPENAI"):
                    async with open_agent("azure"):
                        self.fail("No debe aceptar configuración incompleta")

    async def test_azure_constructs_agent_and_closes_transport_without_network(self):
        with patch.dict(os.environ, {
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "chat",
        }, clear=True):
            async with open_agent("azure") as support:
                self.assertIsInstance(support, AzureAgent)
                self.assertEqual(support.agent.name, "SoporteTI")
                transport = support.agent.client.client
                self.assertFalse(transport.is_closed())
            self.assertTrue(transport.is_closed())

    async def test_real_framework_executes_tools_with_mocked_model(self):
        client = OpenAIChatCompletionClient(
            model="test-deployment",
            azure_endpoint="https://example.openai.azure.com",
            credential=lambda: "not-used",
        )
        tool_calls = [
            {
                "id": "call-search",
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "arguments": json.dumps({"query": "VPN"}),
                },
            },
            {
                "id": "call-status",
                "type": "function",
                "function": {
                    "name": "get_service_status",
                    "arguments": json.dumps({"service": "vpn"}),
                },
            },
        ]

        def completion(message, finish_reason):
            return ChatCompletion.model_validate({
                "id": "test-completion",
                "created": 0,
                "model": "test-deployment",
                "object": "chat.completion",
                "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
            })

        responses = [
            completion({"role": "assistant", "content": None, "tool_calls": tool_calls}, "tool_calls"),
            completion({"role": "assistant", "content": "Datos ficticios: VPN degradada [KB-001]."}, "stop"),
        ]
        async with client.client:
            async with Agent(
                client=client, instructions=INSTRUCTIONS,
                tools=[search_knowledge, get_service_status],
            ) as agent:
                with patch.object(
                    client.client.chat.completions, "create",
                    new_callable=AsyncMock, side_effect=responses,
                ) as model:
                    answer = await AzureAgent(agent).answer("No funciona la VPN")
                    self.assertIn("KB-001", answer)
                    self.assertEqual(model.await_count, 2)
                    messages = model.call_args.kwargs["messages"]
                    tool_results = [message for message in messages if message["role"] == "tool"]
                    self.assertEqual(len(tool_results), 2)
                    self.assertIn("KB-001", str(tool_results))
                    self.assertIn("INC-DEMO-001", str(tool_results))


if __name__ == "__main__":
    unittest.main()
