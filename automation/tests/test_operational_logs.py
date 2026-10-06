import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ..utils.operational_log_audit import (
    CLASS_ALARM,
    CLASS_EVENT,
    CLASS_OPERATIONAL,
    CLASS_SYSTEM,
    WATCHDOG_DESCRIPTION,
    classify_write,
    clip_message,
    normalize_shift,
)


class TestOperationalLogAudit(unittest.TestCase):
    def test_operator_note_is_operational(self):
        self.assertEqual(classify_write(), CLASS_OPERATIONAL)

    def test_event_comment_beats_free_text(self):
        self.assertEqual(classify_write(event_id=12, description="note"), CLASS_EVENT)

    def test_alarm_comment(self):
        self.assertEqual(classify_write(alarm_summary_id=7), CLASS_ALARM)

    def test_watchdog_is_system_not_notebook(self):
        self.assertEqual(
            classify_write(description=WATCHDOG_DESCRIPTION),
            CLASS_SYSTEM,
        )

    def test_shift_whitelist(self):
        self.assertEqual(normalize_shift("Morning"), "morning")
        self.assertIsNone(normalize_shift("weekend"))
        self.assertIsNone(normalize_shift(""))

    def test_message_is_clipped(self):
        text = "x" * 300
        clipped = clip_message(text)
        self.assertLessEqual(len(clipped), 256)
        self.assertTrue(clipped.endswith("…"))


class TestCreateLogJournalsWhenHistorianIsDown(unittest.TestCase):
    def test_create_log_does_not_require_db_live(self):
        from .. import core as core_mod

        user = MagicMock()
        user.username = "operator1"
        envelope = MagicMock()
        envelope.serialize.return_value = {"journaled": True, "message": "nota"}
        app = core_mod.PyAutomation()
        app.sio = MagicMock()
        scope = SimpleNamespace(enabled=False, is_valid=True, area=None)
        with patch.object(app, "_refresh_node_scope", return_value=scope):
            with patch.object(app, "is_db_connected", return_value=False):
                with patch.object(
                    app.logs_engine,
                    "create",
                    return_value=(envelope, "journaled"),
                ) as create:
                    log, status = app.create_log(message="Relevo OK", user=user)

        create.assert_called_once()
        self.assertEqual(log, envelope)
        self.assertEqual(status, "journaled")
        app.sio.emit.assert_called_once()
        self.assertEqual(app.sio.emit.call_args.args[0], "on.log")

    def test_explicit_area_is_kept_for_the_logbook(self):
        from .. import core as core_mod

        user = MagicMock()
        user.username = "operator1"
        app = core_mod.PyAutomation()
        app.sio = None
        scope = SimpleNamespace(enabled=True, is_valid=True, area="Linea1")
        with patch.object(app, "_refresh_node_scope", return_value=scope):
            with patch.object(app.logs_engine, "create", return_value=(MagicMock(), "ok")) as create:
                app.create_log(message="Relevo", user=user, area="Turno noche")

        self.assertEqual(create.call_args.kwargs["area"], "Turno noche")

    def test_blank_area_still_uses_the_node_area(self):
        from .. import core as core_mod

        user = MagicMock()
        user.username = "operator1"
        app = core_mod.PyAutomation()
        app.sio = None
        scope = SimpleNamespace(enabled=True, is_valid=True, area="Linea1")
        with patch.object(app, "_refresh_node_scope", return_value=scope):
            with patch.object(app.logs_engine, "create", return_value=(MagicMock(), "ok")) as create:
                app.create_log(message="Relevo", user=user, area="")

        self.assertEqual(create.call_args.kwargs["area"], "Linea1")

    def test_logger_journals_when_connectivity_fails(self):
        from ..logger.logs import LogsLogger

        user = MagicMock()
        user.username = "operator1"
        logger = LogsLogger()
        with patch.object(logger, "check_connectivity", return_value=False):
            with patch(
                "automation.persistence.outbox.journal_then_remote",
                return_value=(None, True),
            ) as journaled:
                result = logger.create(message="Relevo OK", user=user, shift="night")

        self.assertEqual(journaled.call_args.args[2], False)
        self.assertEqual(result[1], "journaled")
        self.assertTrue(getattr(result[0], "serialize")()["journaled"])
