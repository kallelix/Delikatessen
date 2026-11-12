"""Donnerstagslauf (F-24): Entwurf für die nächste Woche und Push-Nachricht an die Familie."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker

from . import appsettings, planner, push
from .config import Settings

log = logging.getLogger(__name__)

THURSDAY = 3


def next_week_start(today: date) -> date:
    """Der nächste Samstag nach heute: dafür entsteht der Entwurf."""
    return planner.week_start(today) + timedelta(days=7)


def thursday_run(sm: sessionmaker, today: date, sender: push.Sender) -> dict:
    """Erzeugt den Entwurf für die nächste Woche, falls noch keiner besteht, und benachrichtigt die Geräte.

    "Besteht" heißt: mindestens ein Platz der Woche hat schon ein Rezept. Dann bleibt alles, wie es ist,
    und es geht auch keine Nachricht raus.
    """
    with sm() as session:
        settings = appsettings.load(session)
        start = next_week_start(today)
        week = planner.get_or_create_week(session, start, settings)
        if any(s.recipe_id for s in week.slots):
            return {"erzeugt": False, "woche": start.isoformat(), "gesendet": 0}
        planner.generate(session, week, settings, today)
        filled = sum(1 for s in week.slots if s.recipe_id)
        result = push.send_all(
            session,
            sender,
            title="Wochenplan ist da",
            body=f"Der Entwurf für die Woche ab Samstag, {start:%d.%m.} wartet auf euch.",
            url=f"/?woche={start.isoformat()}",
        )
        log.info("Donnerstagslauf: Woche %s, %s Plätze gefüllt, %s Nachrichten", start, filled, result["gesendet"])
        return {"erzeugt": True, "woche": start.isoformat(), "plaetze": filled, **result}


class Scheduler:
    """APScheduler im App-Prozess (Abschnitt 2). Die Uhrzeit kommt aus den Einstellungen und ist änderbar."""

    JOB = "donnerstagslauf"

    def __init__(self, sm: sessionmaker, settings: Settings, sender_factory):
        self.sm = sm
        self.settings = settings
        self.sender_factory = sender_factory
        self.tz = ZoneInfo(settings.timezone)
        self._sched = None

    def today(self) -> date:
        return datetime.now(self.tz).date()

    def run(self) -> dict:
        try:
            return thursday_run(self.sm, self.today(), self.sender_factory(self.settings))
        except Exception:
            log.exception("Donnerstagslauf fehlgeschlagen")
            return {"erzeugt": False, "fehler": True}

    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler

        self._sched = BackgroundScheduler(timezone=self.tz)
        self._sched.start()
        with self.sm() as session:
            plan_time = appsettings.load(session).plan_time
        self.reschedule(plan_time)
        self.catch_up(plan_time)

    def reschedule(self, plan_time: str) -> None:
        if self._sched is None:
            return
        from apscheduler.triggers.cron import CronTrigger

        hour, minute = (int(x) for x in plan_time.split(":"))
        trigger = CronTrigger(day_of_week="thu", hour=hour, minute=minute, timezone=self.tz)
        # misfire_grace_time: kurze Aussetzer (Neustart, Update) werden nachgeholt
        self._sched.add_job(
            self.run, trigger, id=self.JOB, replace_existing=True, misfire_grace_time=6 * 3600, coalesce=True
        )
        log.info("Donnerstagslauf geplant: donnerstags %s", plan_time)

    def catch_up(self, plan_time: str) -> None:
        """War der Dienst zur Uhrzeit aus, holt der Start den Lauf bis Freitagabend nach."""
        now = datetime.now(self.tz)
        hour, minute = (int(x) for x in plan_time.split(":"))
        due = now.weekday() == THURSDAY and (now.hour, now.minute) >= (hour, minute)
        if due or now.weekday() == THURSDAY + 1:
            self._sched.add_job(self.run, id="nachholen", replace_existing=True)

    def shutdown(self) -> None:
        if self._sched is not None:
            self._sched.shutdown(wait=False)
            self._sched = None
