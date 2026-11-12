"""Adapter für Bring! (F-33, Abschnitt 8).

bring-api ist inoffiziell und kann jederzeit brechen. Deshalb kennt nur dieses Modul die Bibliothek,
und jeder Fehler wird zu einer verständlichen BringError-Meldung. Der Rest der App sieht nur BringClient.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

log = logging.getLogger(__name__)

Operation = Literal["add", "complete", "remove"]

MSG_AUTH = "Anmeldung bei Bring! fehlgeschlagen. Bitte E-Mail und Passwort in den Einstellungen prüfen."
MSG_OFFLINE = "Bring! ist gerade nicht erreichbar. Die Liste bleibt in der App, bitte später erneut versuchen."
MSG_CHANGED = (
    "Bring! hat unerwartet geantwortet, vermutlich hat sich die Schnittstelle geändert. "
    "Die Liste bleibt in der App nutzbar, Bring! lässt sich in den Einstellungen abschalten."
)


class BringError(Exception):
    """Fehler mit einer Meldung, die so in der App angezeigt werden kann."""


@dataclass(frozen=True)
class BringList:
    uuid: str
    name: str


@dataclass(frozen=True)
class Change:
    uuid: str
    name: str
    spec: str
    op: Operation


class BringClient(Protocol):
    def lists(self) -> list[BringList]: ...

    def apply(self, list_uuid: str, changes: list[Change]) -> None: ...


class LiveBring:
    """Echter Zugriff. Meldet sich bei jedem Aufruf neu an, abgelaufene Anmeldungen gibt es so nicht."""

    TIMEOUT_S = 20

    def __init__(self, mail: str, password: str):
        self.mail = mail
        self.password = password

    def lists(self) -> list[BringList]:
        async def run(bring):
            res = await bring.load_lists()
            return [BringList(uuid=x.listUuid, name=x.name) for x in res.lists]

        return self._run(run)

    def apply(self, list_uuid: str, changes: list[Change]) -> None:
        if not changes:
            return
        from bring_api import BringItemOperation

        ops = {
            "add": BringItemOperation.ADD,
            "complete": BringItemOperation.COMPLETE,
            "remove": BringItemOperation.REMOVE,
        }

        async def run(bring):
            items = [{"itemId": c.name, "spec": c.spec, "uuid": c.uuid, "operation": ops[c.op]} for c in changes]
            await bring.batch_update_list(list_uuid, items)

        self._run(run)

    def _run(self, fn):
        # Endpunkte laufen synchron im Threadpool, dort gibt es keine laufende Ereignisschleife
        return asyncio.run(self._session(fn))

    async def _session(self, fn):
        import aiohttp
        from bring_api import Bring, BringAuthException, BringRequestException
        from bring_api.exceptions import BringException

        try:
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_S)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                bring = Bring(session, self.mail, self.password)
                await bring.login()
                return await fn(bring)
        except BringAuthException as e:
            raise BringError(MSG_AUTH) from e
        except (BringRequestException, aiohttp.ClientError, TimeoutError) as e:
            log.warning("Bring! nicht erreichbar: %s", type(e).__name__)
            raise BringError(MSG_OFFLINE) from e
        except (BringException, KeyError, TypeError, ValueError, AttributeError) as e:
            log.warning("Bring! unerwartete Antwort: %s", type(e).__name__)
            raise BringError(MSG_CHANGED) from e
