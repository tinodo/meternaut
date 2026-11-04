import logging
import sys
import types
import unittest
from unittest import mock

import support  # noqa: F401  (puts the app folder on the path)

from usage import clients

CLIENT_ID = "11111111-1111-1111-1111-111111111111"
ENDPOINT = "https://account.documents.azure.com:443/"


class ClientsTests(unittest.TestCase):
    def setUp(self):
        identity = types.ModuleType("azure.identity")
        identity.ManagedIdentityCredential = mock.Mock(name="ManagedIdentityCredential")
        cosmos = types.ModuleType("azure.cosmos")
        cosmos.CosmosClient = mock.Mock(name="CosmosClient")
        query = types.ModuleType("azure.monitor.query")
        query.LogsQueryClient = mock.Mock(name="LogsQueryClient")
        self.identity, self.cosmos, self.query = identity, cosmos, query
        patcher = mock.patch.dict(sys.modules, {"azure.identity": identity, "azure.cosmos": cosmos, "azure.monitor.query": query})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.clear_caches()
        self.addCleanup(self.clear_caches)

    @staticmethod
    def clear_caches():
        for cached in (clients.credential, clients.cosmos_client, clients.logs_client):
            cached.cache_clear()

    def test_the_credential_is_the_managed_identity_with_its_client_id_and_nothing_else(self):
        credential = clients.credential(CLIENT_ID)
        self.identity.ManagedIdentityCredential.assert_called_once_with(client_id=CLIENT_ID)
        self.assertIs(credential, self.identity.ManagedIdentityCredential.return_value)

    def test_a_client_is_built_once_and_reused(self):
        self.assertIs(clients.credential(CLIENT_ID), clients.credential(CLIENT_ID))
        self.assertIs(clients.cosmos_client(CLIENT_ID, ENDPOINT), clients.cosmos_client(CLIENT_ID, ENDPOINT))
        self.assertIs(clients.logs_client(CLIENT_ID), clients.logs_client(CLIENT_ID))
        self.assertEqual(self.identity.ManagedIdentityCredential.call_count, 1)
        self.assertEqual(self.cosmos.CosmosClient.call_count, 1)
        self.assertEqual(self.query.LogsQueryClient.call_count, 1)

    def test_the_cosmos_client_gets_the_endpoint_and_the_credential_only(self):
        clients.cosmos_client(CLIENT_ID, ENDPOINT)
        self.cosmos.CosmosClient.assert_called_once_with(ENDPOINT, credential=self.identity.ManagedIdentityCredential.return_value)

    def test_the_container_is_found_by_database_and_container_name(self):
        container = clients.cosmos_container(CLIENT_ID, ENDPOINT, "usage-db", "llm-container")
        client = self.cosmos.CosmosClient.return_value
        client.get_database_client.assert_called_once_with("usage-db")
        client.get_database_client.return_value.get_container_client.assert_called_once_with("llm-container")
        self.assertIs(container, client.get_database_client.return_value.get_container_client.return_value)

    def test_the_logs_client_gets_the_credential_only(self):
        clients.logs_client(CLIENT_ID)
        self.query.LogsQueryClient.assert_called_once_with(self.identity.ManagedIdentityCredential.return_value)

    def test_one_credential_serves_both_clients(self):
        clients.cosmos_client(CLIENT_ID, ENDPOINT)
        clients.logs_client(CLIENT_ID)
        self.assertEqual(self.identity.ManagedIdentityCredential.call_count, 1)

    def test_another_identity_gets_another_credential(self):
        clients.credential(CLIENT_ID)
        clients.credential("22222222-2222-2222-2222-222222222222")
        self.assertEqual(self.identity.ManagedIdentityCredential.call_count, 2)

    def test_the_sdks_log_warnings_and_errors_only(self):
        for name in ("azure", "azure.cosmos", "azure.core.pipeline.policies.http_logging_policy", "azure.monitor.query"):
            with self.subTest(logger=name):
                self.assertFalse(logging.getLogger(name).isEnabledFor(logging.INFO))
                self.assertTrue(logging.getLogger(name).isEnabledFor(logging.WARNING))


if __name__ == "__main__":
    unittest.main()
