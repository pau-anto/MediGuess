"""Stockage clé -> document du backend MediGuess.

Quatre « tables » : cases (cas en cours), games (parties), users (comptes),
scores (parties terminées des joueurs connectés).

- MemoryStore : des dicts Python. Tests et dev local à une seule instance.
- TableStore : Azure Table Storage. Obligatoire sur Azure : l'API peut avoir
  plusieurs instances ou être éteinte (scale-to-zero), sa mémoire est perdue.

Le choix se fait par variable d'environnement (cf. make_store) : le même
code tourne en local, avec l'émulateur Azurite, et sur Azure.
"""

import copy
import os
from collections import defaultdict


class Conflict(Exception):
    """La clé existe déjà (ex. pseudo déjà pris)."""


class MemoryStore:
    def __init__(self):
        self._tables = defaultdict(dict)

    def insert(self, table, key, data):
        if key in self._tables[table]:
            raise Conflict(key)
        self._tables[table][key] = copy.deepcopy(data)

    def upsert(self, table, key, data):
        self._tables[table][key] = copy.deepcopy(data)

    def get(self, table, key):
        data = self._tables[table].get(key)
        return copy.deepcopy(data) if data is not None else None

    def pop(self, table, key):
        """Lit puis efface, en une seule opération (un cas ne se joue qu'une fois).
        Sert aussi de suppression simple."""
        return self._tables[table].pop(key, None)

    def query(self, table, **equals):
        """Documents dont les champs valent `equals` ; la clé est dans « _key »."""
        return [
            {**copy.deepcopy(data), "_key": key}
            for key, data in self._tables[table].items()
            if all(data.get(k) == v for k, v in equals.items())
        ]


class TableStore:
    """Une table Azure par « table », une seule partition, RowKey = clé."""

    PARTITION = "mg"

    def __init__(self, connection_string, prefix=""):
        # Import local : la dépendance Azure n'est requise qu'en prod.
        from azure.data.tables import TableServiceClient  # pylint: disable=C0415

        self._service = TableServiceClient.from_connection_string(connection_string)
        self._prefix = prefix
        self._clients = {}

    def _table(self, name):
        if name not in self._clients:
            self._clients[name] = self._service.create_table_if_not_exists(
                self._prefix + name
            )
        return self._clients[name]

    def _entity(self, key, data):
        return {"PartitionKey": self.PARTITION, "RowKey": key, **data}

    @staticmethod
    def _clean(entity):
        return {
            k: v for k, v in dict(entity).items() if k not in ("PartitionKey", "RowKey")
        }

    def insert(self, table, key, data):
        from azure.core.exceptions import ResourceExistsError  # pylint: disable=C0415

        try:
            self._table(table).create_entity(self._entity(key, data))
        except ResourceExistsError as err:
            raise Conflict(key) from err

    def upsert(self, table, key, data):
        from azure.data.tables import UpdateMode  # pylint: disable=C0415

        self._table(table).upsert_entity(
            self._entity(key, data), mode=UpdateMode.REPLACE
        )

    def get(self, table, key):
        from azure.core.exceptions import ResourceNotFoundError  # pylint: disable=C0415

        try:
            return self._clean(self._table(table).get_entity(self.PARTITION, key))
        except ResourceNotFoundError:
            return None

    def pop(self, table, key):
        # pylint: disable=C0415
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError

        client = self._table(table)
        try:
            entity = client.get_entity(self.PARTITION, key)
            # Suppression conditionnelle (etag) : si deux requêtes arrivent en
            # même temps pour la même clé, une seule gagne.
            client.delete_entity(
                self.PARTITION,
                key,
                etag=entity.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (ResourceNotFoundError, ResourceModifiedError):
            return None
        return self._clean(entity)

    def query(self, table, **equals):
        client = self._table(table)
        if not equals:
            entities = client.list_entities()
        else:
            entities = client.query_entities(
                " and ".join(f"{k} eq @{k}" for k in equals), parameters=equals
            )
        return [{**self._clean(e), "_key": e["RowKey"]} for e in entities]


def make_store():
    """AZURE_STORAGE_CONNECTION_STRING défini -> Table Storage, sinon mémoire."""
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if connection_string:
        return TableStore(connection_string)
    return MemoryStore()
