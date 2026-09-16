import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from .states import (
    AlarmState,
    AlarmAttrs,
    history_name_from_isa,
    HISTORY_CLEARED,
    HISTORY_NORMAL,
    HISTORY_UNACK,
    HISTORY_ACK,
    HISTORY_RTNUN,
    HISTORY_SUPPRESSED,
    sm_value_from_isa,
    isa_name_from_history,
)
from .trigger import Trigger, TriggerType
from .delays import (
    DEFAULT_ALARM_DELAY_S,
    DEFAULT_ALARM_DELAY_UNITS,
    clamp_alarm_delay,
    normalize_delay_units,
)
from ..tags.tag import Tag
from .runtime import (
    AlarmTagObserver,
    KIND_ABNORMAL,
    KIND_EMIT,
    KIND_NORMAL,
    KIND_UNSHELVE,
    get_alarm_runtime,
)
from .config import AlarmConfig
from ..tags.cvt import CVTEngine
from ..modules.users.users import User
from ..utils.decorators import validate_types, logging_error_handler, set_event, put_alarm_state
from ..models import FloatType, IntegerType, StringType
from ..variables import *
from statemachine import State, StateMachine
from flask_socketio import SocketIO


class Alarm(StateMachine):
    r"""
    Represents an Alarm entity with state machine logic.

    Implements the standard alarm lifecycle defined in ISA 18.2, including states like
    Normal, Unacknowledged, Acknowledged, Shelved, and Suppressed.

    It monitors a `Tag` value against a `Trigger` condition and transitions states accordingly.
    """

    # MAIN STATES
    normal = State("normal", initial=True)
    unack_alarm = State("unack_alarm")
    ack_alarm = State("ack_alarm")
    rtn_unack = State("rtn_unack")

    # OUT OF SERVICE STATES
    shelved = State("shelved")
    suppressed_by_design = State("suppressed_by_design")
    out_of_service = State("out_of_service")

    # MAIN TRANSITIONS
    normal_to_unack_alarm = normal.to(unack_alarm)
    unack_alarm_to_ack_alarm = unack_alarm.to(ack_alarm)
    ack_alarm_to_normal = ack_alarm.to(normal)
    unack_alarm_to_rtn_unack = unack_alarm.to(rtn_unack)
    rtn_unack_to_normal = rtn_unack.to(normal)
    rtn_unack_to_unack_alarm = rtn_unack.to(unack_alarm)

    # SHELVED TRANSITIONS
    normal_to_shelved = normal.to(shelved)
    unack_alarm_to_shelved = unack_alarm.to(shelved)
    ack_alarm_to_shelved = ack_alarm.to(shelved)
    rtn_unack_to_shelved = rtn_unack.to(shelved)
    shelved_to_normal = shelved.to(normal)
    shelved_to_unack_alarm = shelved.to(unack_alarm)

    # SUPPRESSED BY DESIGN TRANSITIONS
    normal_to_suppressed_by_design = normal.to(suppressed_by_design)
    unack_alarm_to_suppressed_by_design = unack_alarm.to(suppressed_by_design)
    ack_alarm_to_suppressed_by_design = ack_alarm.to(suppressed_by_design)
    rtn_unack_to_suppressed_by_design = rtn_unack.to(suppressed_by_design)
    suppressed_by_design_to_normal = suppressed_by_design.to(normal)
    suppressed_by_design_to_unack_alarm = suppressed_by_design.to(unack_alarm)


    # OUT OF SERVICE TRANSITIONS
    normal_to_out_of_service = normal.to(out_of_service)
    unack_alarm_to_out_of_service = unack_alarm.to(out_of_service)
    ack_alarm_to_out_of_service = ack_alarm.to(out_of_service)
    rtn_unack_to_out_of_service = rtn_unack.to(out_of_service)
    out_of_service_to_normal = out_of_service.to(normal)
    out_of_service_to_unack_alarm = out_of_service.to(unack_alarm)

    # ISA-18.2 On-Delay / Off-Delay. Tests may disable wall-clock wakeups.
    enable_delay_wakeups = True
    _quality_fns = None

    def __init__(
            self,
            name:str, 
            tag:Tag,
            alarm_type:StringType,
            alarm_setpoint:IntegerType|FloatType,
            description:str="",
            state:str=None,
            timestamp:datetime=None,
            ack_timestamp:datetime=None,
            alarm_deadband:IntegerType|FloatType=FloatType(0.0),
            alarm_on_delay:IntegerType|FloatType=FloatType(DEFAULT_ALARM_DELAY_S),
            alarm_off_delay:IntegerType|FloatType=FloatType(DEFAULT_ALARM_DELAY_S),
            identifier:str=None,
            user:User=None,
            reload:bool=False,
            on_delay_units:str=DEFAULT_ALARM_DELAY_UNITS,
            off_delay_units:str=DEFAULT_ALARM_DELAY_UNITS,
        ):
        r"""
        Initializes the Alarm.

        **Parameters:**

        * **name** (str): Alarm name.
        * **tag** (Tag): The tag being monitored.
        * **alarm_type** (StringType): Trigger type (HI, LO, etc.).
        * **alarm_setpoint** (IntegerType|FloatType): The limit value.
        * **description** (str): Alarm description.
        * **state** (str, optional): Initial state.
        * **identifier** (str, optional): Unique ID.
        """
        from ..logger.alarms import AlarmsLoggerEngine
        self.alarm_engine = AlarmsLoggerEngine()
        self.tag_engine = CVTEngine()
        self.name = name
        self.tag = tag
        # Verificar que tag no sea None antes de acceder a sus atributos
        if tag is None:
            raise ValueError(f"Cannot create alarm '{name}': tag is None")
        self.segment = tag.segment if hasattr(tag, 'segment') else None
        self.manufacturer = tag.manufacturer if hasattr(tag, 'manufacturer') else None
        self.attach(machine=self, tag=tag)
        self.description = description        
        self.alarm_setpoint = Trigger()
        self.alarm_setpoint.type = TriggerType(value=alarm_type.value.upper())
        self.alarm_setpoint.value = alarm_setpoint.value
        alarm_deadband.unit = tag.get_display_unit()
        self.alarm_deadband = alarm_deadband
        self.alarm_on_delay = FloatType(clamp_alarm_delay(alarm_on_delay))
        self.alarm_off_delay = FloatType(clamp_alarm_delay(alarm_off_delay))
        self.on_delay_units = normalize_delay_units(on_delay_units)
        self.off_delay_units = normalize_delay_units(off_delay_units)
        self.priority = 3
        self.latching = True
        self.ack_required = True
        self.chattering = False
        self.chatter_count = 0
        self.last_chatter_ts = None
        self._condition_met = False
        self._on_timer_start = None
        self._off_timer_start = None
        self._last_eval_epoch = None
        self._delay_wakeup_job = None
        self.timestamp = timestamp 
        self.ack_timestamp = ack_timestamp
        self.state = AlarmState.NORM
        if state:
            
            for _, attr in AlarmState.__dict__.items():
                
                if isinstance(attr, AlarmAttrs):
                    
                    if state==attr.state:
                        
                        self.state = attr
                        break
        if identifier:
            self.identifier = identifier
        else:
            self.identifier = secrets.token_hex(4)

        self._shelved_time:datetime = None
        self._shelved_until:datetime = None
        self._shelved_options_time = {
            'days': 0,
            'seconds': 0,
            'microseconds': 0,
            'milliseconds': 0,
            'minutes': 0,
            'hours': 0,
            'weeks': 0
        }
        catalog_state = state
        transitions = []
        for sm_state in self.states:
            transitions.extend(sm_state.transitions)
        self.transitions = transitions
        self.sio:SocketIO|None = None
        self._defer_persist = False
        self._suppress_enter_hooks = True
        self._last_history_state = HISTORY_NORMAL
        self._pending_operator_id = None
        self.last_transition_ts = None
        self.last_transition_from = None
        self.last_transition_to = None
        self._runtime = get_alarm_runtime()
        super(Alarm, self).__init__()
        self._suppress_enter_hooks = False
        if reload and catalog_state and str(catalog_state) not in ("Normal", HISTORY_NORMAL, ""):
            self._force_state(catalog_state)

    def catalog_payload(self) -> dict:
        r"""Fields needed to persist this alarm definition to the historian catalog."""
        tag_name = None
        area = None
        tag = self.tag
        if tag is not None:
            tag_name = getattr(tag, "name", None)
            if not tag_name:
                getter = getattr(tag, "get_name", None)
                if callable(getter):
                    tag_name = getter()
            area = getattr(tag, "area", None)
        if not area:
            from ..utils.event_scope import resolve_event_area

            area = resolve_event_area()
        trigger = self.alarm_setpoint
        trigger_type = None
        trigger_value = None
        if trigger is not None:
            trigger_value = getattr(trigger, "value", None)
            kind = getattr(trigger, "type", None)
            if kind is not None:
                trigger_type = getattr(kind, "value", None) or str(kind)
        return {
            "identifier": self.identifier,
            "tag": tag_name,
            "trigger_type": trigger_type or "BOOL",
            "trigger_value": trigger_value,
            "description": self.description or "",
            "area": area,
            "on_delay": self._on_delay_s(),
            "off_delay": self._off_delay_s(),
            "on_delay_units": self.on_delay_units,
            "off_delay_units": self.off_delay_units,
        }

    def _current_condition_value(self):
        tag = getattr(self, "tag", None)
        if tag is None:
            return None
        value = getattr(tag, "value", None)
        if value is None:
            return None
        numeric = getattr(value, "value", value)
        try:
            return float(numeric)
        except (TypeError, ValueError):
            return None

    def _operator_pk(self, user:User=None, operator_id:int=None):
        if operator_id is not None:
            try:
                return int(operator_id)
            except (TypeError, ValueError):
                return None
        if user is None:
            return None
        for attr in ("pk", "id"):
            raw = getattr(user, attr, None)
            if isinstance(raw, int):
                return raw
        username = getattr(user, "username", None)
        if not username:
            return None
        try:
            from ..dbmodels.users import Users

            row = Users.read_by_username(username=username)
            if row is not None:
                return row.id
        except Exception:
            return None
        return None

    def _force_state(self, state:str) -> None:
        """Restore SM from catalog without on_enter_* / history (P1-3)."""
        history = history_name_from_isa(state)
        sm_value = sm_value_from_isa(state)
        self._suppress_enter_hooks = True
        try:
            self.current_state_value = sm_value
        except Exception:
            pass
        self._suppress_enter_hooks = False
        isa = isa_name_from_history(history)
        mapped = None
        try:
            mapped = AlarmState.get_state_by_name(isa) if isa else None
        except Exception:
            mapped = None
        if mapped is not None:
            self.state = mapped
        elif history == HISTORY_UNACK:
            self.state = AlarmState.UNACK
        elif history == HISTORY_ACK:
            self.state = AlarmState.ACKED
        elif history == HISTORY_RTNUN:
            self.state = AlarmState.RTNUN
        else:
            self.state = AlarmState.NORM
        self._last_history_state = HISTORY_NORMAL if history == HISTORY_CLEARED else history

    def _record_transition(self, from_state:str, to_state:str, *, operator_id:int=None) -> bool:
        """Single writer for alarm_summary. INV-01, INV-02, INV-07."""
        if getattr(self, "_suppress_enter_hooks", False):
            return False
        if getattr(self, "_defer_persist", False):
            self._last_history_state = to_state if to_state != HISTORY_CLEARED else HISTORY_NORMAL
            return False
        if from_state == to_state:
            return False
        from .p2.latching import LatchingPolicyRegistry

        policy = LatchingPolicyRegistry.for_alarm(self)
        to_state = policy.adjust_target_state(from_state, to_state)
        if not policy.should_record(from_state, to_state):
            return False
        runtime = get_alarm_runtime()
        if (from_state, to_state) in (("Unack Alarm", "RTN Unack"), ("RTN Unack", "Unack Alarm")):
            if runtime.chatter.on_transition(self, from_state, to_state):
                runtime.kpi.record_chatter(1)
        if to_state in HISTORY_SUPPRESSED:
            logging.getLogger("pyautomation").warning(
                "ALM.SUPPRESSED.Skipped history for %s alarm=%s",
                to_state,
                self.name,
            )
            self._last_history_state = to_state
            return False
        from ..timebase import quantize_datetime_ms

        now = quantize_datetime_ms(datetime.now(timezone.utc))
        self.last_transition_ts = now
        self.last_transition_from = from_state
        self.last_transition_to = to_state
        ack_ts = self.ack_timestamp if to_state in (HISTORY_ACK, HISTORY_CLEARED) else None
        catalog = self.catalog_payload()
        persist_state = isa_name_from_history(to_state)
        self.alarm_engine.create_record_on_alarm_summary(
            name=self.name,
            state=persist_state,
            timestamp=now,
            ack_timestamp=ack_ts,
            identifier=catalog.get("identifier"),
            tag=catalog.get("tag"),
            trigger_type=catalog.get("trigger_type"),
            trigger_value=catalog.get("trigger_value"),
            description=catalog.get("description"),
            area=catalog.get("area"),
            from_state=from_state,
            to_state=to_state,
            event_time=now,
            operator_id=operator_id if operator_id is not None else self._pending_operator_id,
            condition_met=bool(self._condition_met),
            condition_value=self._current_condition_value(),
            schema_version=2,
            last_transition_ts=now,
            last_transition_from=from_state,
            last_transition_to=to_state,
        )
        self._last_history_state = HISTORY_NORMAL if to_state == HISTORY_CLEARED else to_state
        self._pending_operator_id = None
        try:
            runtime = get_alarm_runtime()
            runtime.note_history_insert()
            runtime.sync_alarm(self)
        except Exception:
            pass
        return True

    @logging_error_handler
    @put_alarm_state
    def on_enter_normal(self):
        if getattr(self, "_suppress_enter_hooks", False):
            self.state = AlarmState.NORM
            return
        prior = self._last_history_state or HISTORY_NORMAL
        self.state = AlarmState.NORM
        self.ack_timestamp = None
        self._reset_delay_timers()
        if prior in (HISTORY_ACK, HISTORY_RTNUN, HISTORY_UNACK):
            self.timestamp = None
            self._record_transition(prior, HISTORY_CLEARED)
        elif prior not in HISTORY_SUPPRESSED:
            self.timestamp = None

    @logging_error_handler
    @put_alarm_state
    def on_enter_unack_alarm(self):
        if getattr(self, "_suppress_enter_hooks", False):
            self.state = AlarmState.UNACK
            return
        from ..timebase import quantize_datetime_ms
        prior = self._last_history_state or HISTORY_NORMAL
        self.state = AlarmState.UNACK
        stamp = getattr(self, "_Alarm__timestamp", None)
        if not isinstance(stamp, datetime):
            stamp = datetime.now(timezone.utc)
        if self.timestamp is None:
            self.timestamp = quantize_datetime_ms(stamp)
        self._record_transition(prior, HISTORY_UNACK)
        if not bool(getattr(self, "ack_required", True)):
            self._apply_acknowledge(datetime.now(timezone.utc))

    @logging_error_handler
    @put_alarm_state
    def on_enter_ack_alarm(self):
        if getattr(self, "_suppress_enter_hooks", False):
            self.state = AlarmState.ACKED
            return
        from ..timebase import quantize_datetime_ms
        prior = self._last_history_state or HISTORY_UNACK
        self.state = AlarmState.ACKED
        stamp = getattr(self, "_Alarm__timestamp", None)
        if not isinstance(stamp, datetime):
            stamp = datetime.now(timezone.utc)
        self.ack_timestamp = quantize_datetime_ms(stamp)
        self._record_transition(prior, HISTORY_ACK, operator_id=self._pending_operator_id)

    @logging_error_handler
    @put_alarm_state
    def on_enter_rtn_unack(self):
        if getattr(self, "_suppress_enter_hooks", False):
            self.state = AlarmState.RTNUN
            return
        prior = self._last_history_state or HISTORY_UNACK
        self.state = AlarmState.RTNUN
        if bool(getattr(self, "latching", True)):
            self._record_transition(prior, HISTORY_RTNUN)

    @logging_error_handler
    @put_alarm_state
    def on_enter_shelved(self):
        
        self.state = AlarmState.SHLVD
        self._reset_delay_timers()

    @logging_error_handler
    @put_alarm_state
    def on_enter_suppressed_by_design(self):
        
        self.state = AlarmState.DSUPR
        self._reset_delay_timers()

    @logging_error_handler
    @put_alarm_state
    def on_enter_out_of_service(self):
        
        self.state = AlarmState.OOSRV
        self._reset_delay_timers()

    def set_socketio(self, sio:SocketIO):
        r"""
        Sets the SocketIO instance for real-time updates.

        **Parameters:**

        * **sio** (SocketIO): The SocketIO server instance.
        """
        self.sio:SocketIO = sio

    @logging_error_handler
    @validate_types(
            tag=str, 
            value=Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|Volume|MassFlow|Density|Percentage|Adimentional, 
            timestamp=(datetime, type(None)), 
            output=None)
    def notify(
        self, 
        tag:str, 
        value:Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow|Volume|MassFlow|Density|Percentage|Adimentional, 
        timestamp:datetime|None):
        r"""
        Callback triggered when the monitored Tag value changes (Observer pattern).
        
        It evaluates the new value against alarm logic and triggers state transitions.
        Process setpoints are inhibited while the PV quality is BAD (configurable
        for UNCERTAIN via ``alarm_inhibit_uncertain_quality``).

        **Parameters:**

        * **tag** (str): Tag name.
        * **value** (Quantity): The new tag value.
        * **timestamp** (datetime): Time of the value change. ``None`` is ignored
          (tag never had a last-good sample).
        """ 
        if timestamp is None:
            return
        numeric = getattr(value, "value", value)
        self.check_condition(numeric, timestamp)

    def check_condition(self, pv_value, timestamp=None) -> str | None:
        """O(1) condition + delay tick. No SM, no INSERT, no socket.

        Returns a queued kind or None. SPEC-ISA18-2-CLOSURE-v2 INV-21.
        """
        runtime = get_alarm_runtime()
        started = time.perf_counter()
        try:
            return self._check_condition_impl(pv_value, timestamp)
        finally:
            runtime.latency.observe_us((time.perf_counter() - started) * 1_000_000.0)
            # INV-42: production never drains on the hot path.
            if AlarmConfig.is_sync_drain_allowed() and not runtime.is_worker_alive_recently():
                runtime.drain()

    def check_condition_from_tag(self, tag) -> str | None:
        timestamp = getattr(tag, "timestamp", None)
        value = getattr(tag, "value", None)
        numeric = getattr(value, "value", value) if value is not None else None
        return self.check_condition(numeric, timestamp)

    def _check_condition_impl(self, pv_value, timestamp) -> str | None:
        if timestamp is None:
            return None
        self.__timestamp = timestamp
        state = self.state
        if state == AlarmState.SHLVD:
            until = getattr(self, "_shelved_until", None)
            if until is not None and datetime.now(timezone.utc) >= until:
                self._enqueue_hotpath(KIND_UNSHELVE)
                return KIND_UNSHELVE
            return None
        if state in (AlarmState.DSUPR, AlarmState.OOSRV):
            return None
        runtime = get_alarm_runtime()
        ident = getattr(self, "identifier", None) or getattr(self, "name", None)
        if ident and runtime.suppression.is_suppressed(ident):
            return None
        if self._is_iad_alarm():
            condition_met = self._iad_condition_met()
        elif self._quality_allows_process_evaluation():
            condition_met = self._process_condition_met(pv_value)
        else:
            return None
        return self._evaluate_delays(condition_met, timestamp)

    def _enqueue_hotpath(self, kind: str) -> None:
        runtime = getattr(self, "_runtime", None) or get_alarm_runtime()
        runtime.enqueue(self, kind)

    def _is_iad_alarm(self) -> bool:
        name = (getattr(self, "name", None) or "").lower()
        return name.endswith(".iad") or name.startswith("alarm.iad.") or ".iad." in name

    def _is_quality_alarm(self) -> bool:
        """Instrument-quality BOOL (ALM.QUALITY.*), not a process setpoint."""
        name = (getattr(self, "name", None) or "").lower()
        return ".alm.quality." in name or name.startswith("alm.quality.")

    def _is_performance_alarm(self) -> bool:
        """Node diagnostic BOOL (ALM.PERF.*): hub lag, CPU, SAF, … — not a process trip."""
        name = (getattr(self, "name", None) or "").lower()
        return ".alm.perf." in name or name.startswith("alm.perf.")

    def _is_auto_clear_alarm(self) -> bool:
        """Leave Active as soon as the condition clears; do not latch RTN Unacknowledged."""
        return self._is_quality_alarm() or self._is_performance_alarm()

    def _iad_condition_met(self) -> bool:
        """IAD alarms follow signal quality, not the analog PV as BOOL."""
        from ..signal_conditioning.quality import GOOD, is_good_quality

        tag = getattr(self, "tag", None)
        if tag is None:
            return False
        quality = getattr(tag, "quality", GOOD)
        stale = bool(getattr(tag, "stale", False))
        return stale or not is_good_quality(quality)

    def _on_delay_s(self) -> float:
        return clamp_alarm_delay(self.alarm_on_delay)

    def _off_delay_s(self) -> float:
        return clamp_alarm_delay(self.alarm_off_delay)

    def _epoch(self, timestamp: datetime | None) -> float:
        if timestamp is None:
            return time.time()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.timestamp()

    def _is_process_active(self) -> bool:
        current = getattr(self.current_state, "name", "") or ""
        return current.lower() in ("unack_alarm", "ack_alarm")

    def _process_condition_met(self, numeric_value) -> bool:
        if numeric_value is None:
            return False
        kind = self.alarm_setpoint.type
        setpoint = self.alarm_setpoint.value
        deadband = float(getattr(self.alarm_deadband, "value", self.alarm_deadband) or 0.0)
        active = self._is_process_active()
        if kind in (TriggerType.HH, TriggerType.H):
            if active and deadband > 0.0:
                return numeric_value >= (setpoint - deadband)
            return numeric_value > setpoint
        if kind in (TriggerType.L, TriggerType.LL):
            if active and deadband > 0.0:
                return numeric_value <= (setpoint + deadband)
            return numeric_value < setpoint
        return bool(numeric_value) == bool(setpoint)

    def _reset_delay_timers(self) -> None:
        self._on_timer_start = None
        self._off_timer_start = None
        self._cancel_delay_wakeup()

    def _cancel_delay_wakeup(self) -> None:
        job = getattr(self, "_delay_wakeup_job", None)
        if job is None:
            return
        self._delay_wakeup_job = None
        killer = getattr(job, "kill", None)
        if callable(killer):
            try:
                killer()
                return
            except Exception:
                pass
        cancel = getattr(job, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass

    def _delay_phase(self) -> str | None:
        if self._on_timer_start is not None and not self._is_process_active() and self._condition_met:
            return "pending"
        if self._off_timer_start is not None and self._is_process_active() and not self._condition_met:
            return "clearing"
        return None

    def _timer_remaining(self, start: float | None, delay_s: float) -> float | None:
        if start is None:
            return None
        now = self._last_eval_epoch
        if now is None:
            return None
        wall = time.time()
        if abs(wall - now) < 2.0:
            now = wall
        remaining = delay_s - (now - start)
        return max(0.0, round(remaining, 1))

    def _remaining_wakeup_s(self) -> float | None:
        now = self._last_eval_epoch
        if now is None:
            return None
        if self._on_timer_start is not None and not self._is_process_active():
            return max(0.0, self._on_delay_s() - (now - self._on_timer_start))
        if self._off_timer_start is not None and self._is_process_active():
            return max(0.0, self._off_delay_s() - (now - self._off_timer_start))
        return None

    def _schedule_delay_wakeup(self) -> None:
        self._cancel_delay_wakeup()
        if not getattr(self, "enable_delay_wakeups", True):
            return
        remaining = self._remaining_wakeup_s()
        if remaining is None:
            return
        now = self._last_eval_epoch
        if now is not None and abs(time.time() - now) > 2.0:
            # Synthetic / historical timestamps: tests drive time via notify().
            return
        delay = max(0.0, remaining)
        try:
            import gevent

            self._delay_wakeup_job = gevent.spawn_later(delay, self._delay_wakeup)
            return
        except Exception:
            pass
        import threading

        timer = threading.Timer(delay, self._delay_wakeup)
        timer.daemon = True
        timer.start()
        self._delay_wakeup_job = timer

    def _delay_wakeup(self) -> None:
        self._delay_wakeup_job = None
        tag = getattr(self, "tag", None)
        if tag is None:
            return
        value = getattr(tag, "value", None)
        if value is None:
            return
        name = getattr(tag, "name", None)
        if not name:
            return
        self.notify(tag=name, value=value, timestamp=datetime.now(timezone.utc))

    def serialize_socket(self):
        """INV-47: compact on.alarm payload (≤ 2 KB). HMI-compatible top-level keys."""
        from ..timebase import iso_millis

        state = self.state
        state_payload = state.serialize() if hasattr(state, "serialize") else str(state)
        return {
            "event": "state_change",
            "identifier": self.identifier,
            "id": self.identifier,
            "name": self.name,
            "tag": getattr(self.tag, "name", None),
            "state": state_payload,
            "last_transition_ts": iso_millis(getattr(self, "last_transition_ts", None)),
            "last_transition_from": getattr(self, "last_transition_from", None),
            "last_transition_to": getattr(self, "last_transition_to", None),
            "from_state": getattr(self, "last_transition_from", None),
            "to_state": getattr(self, "last_transition_to", None),
            "timestamp": iso_millis(self.timestamp),
            "delay_phase": self._delay_phase(),
            "condition_met": bool(self._condition_met),
            "description": self.description,
            "priority": int(getattr(self, "priority", 3) or 3),
            "latching": bool(getattr(self, "latching", True)),
            "ack_required": bool(getattr(self, "ack_required", True)),
            "chattering": bool(getattr(self, "chattering", False)),
        }

    def _emit_runtime_state(self) -> None:
        sio = getattr(self, "sio", None)
        if not sio:
            return
        try:
            sio.emit("on.alarm", data=self.serialize_socket())
        except Exception:
            pass

    def _evaluate_delays(self, condition_met: bool, timestamp: datetime) -> str | None:
        previous_phase = self._delay_phase()
        now = self._epoch(timestamp)
        self._last_eval_epoch = now
        self._condition_met = bool(condition_met)
        alarm_active = self._is_process_active()
        on_delay = self._on_delay_s()
        off_delay = self._off_delay_s()
        intent = None

        if condition_met:
            self._off_timer_start = None
            if not alarm_active:
                if self._on_timer_start is None:
                    self._on_timer_start = now
                if (now - self._on_timer_start) >= on_delay:
                    intent = KIND_ABNORMAL
                    self._on_timer_start = None
                    self._off_timer_start = None
            else:
                self._on_timer_start = None
        else:
            self._on_timer_start = None
            if alarm_active:
                if self._off_timer_start is None:
                    self._off_timer_start = now
                if (now - self._off_timer_start) >= off_delay:
                    intent = KIND_NORMAL
                    self._off_timer_start = None
                    self._on_timer_start = None
            else:
                self._off_timer_start = None

        if on_delay or off_delay:
            self._schedule_delay_wakeup()
        phase = self._delay_phase()
        if intent:
            self._enqueue_hotpath(intent)
        elif phase or previous_phase:
            self._enqueue_hotpath(KIND_EMIT)
        return intent

    def _quality_allows_process_evaluation(self) -> bool:
        """Gate process setpoints on PV quality (ISA-18.2 inhibit on Bad)."""
        fns = Alarm._quality_fns
        if fns is None:
            from ..signal_conditioning.quality import (
                get_inhibit_uncertain_quality,
                is_process_alarm_allowed,
            )

            Alarm._quality_fns = (is_process_alarm_allowed, get_inhibit_uncertain_quality)
            fns = Alarm._quality_fns
        is_allowed, get_inhibit = fns
        subject = getattr(self, "tag", None)
        quality = getattr(subject, "quality", None) if subject is not None else None
        try:
            inhibit_uncertain = bool(get_inhibit())
        except Exception:
            inhibit_uncertain = False
        return is_allowed(quality, inhibit_uncertain=inhibit_uncertain)

    @logging_error_handler
    def abnormal_condition(self):
        r"""
        Triggers transition to an alarm state (abnormal).

        Already Unacknowledged: no-op (ISA-18.2 does not re-annunciate).
        """
        current_state = self.current_state.name.lower()
        if current_state == "unack_alarm":
            return
        transition_name = f'{current_state}_to_unack_alarm'
        self.__transition(transition_name=transition_name)

    @logging_error_handler
    def normal_condition(self):
        r"""
        Triggers transition to normal or return-to-normal states.

        Process alarms: RTN Unacknowledged until the operator acks (ISA-18.2).
        ``ALM.QUALITY.*`` and ``ALM.PERF.*`` auto-clear to Normal when the
        condition is gone so diagnostic tiles do not stay Active/RTNUN.
        """
        current_state = self.current_state.name.lower()
        auto_clear = self._is_auto_clear_alarm()

        if current_state=="unack_alarm":

            transition_name = f'{current_state}_to_rtn_unack'
            self.__transition(transition_name=transition_name)
            if auto_clear or not bool(getattr(self, "latching", True)):
                self._apply_acknowledge(datetime.now(timezone.utc))

        elif current_state=="ack_alarm":

            transition_name = f'{current_state}_to_normal'
            self.__transition(transition_name=transition_name)

        elif current_state=="rtn_unack" and auto_clear:

            self._apply_acknowledge(datetime.now(timezone.utc))

    def _apply_acknowledge(self, now:datetime)->bool:
        r"""
        ISA-18.2 acknowledge transition in memory only.

        Persistence, audit, and socket fan-out are owned by the caller so a
        bulk acknowledge can pay one round-trip instead of one per alarm.
        """
        current_state = self.current_state.name.lower()
        if current_state == "unack_alarm":
            transition_name = "unack_alarm_to_ack_alarm"
        elif current_state == "rtn_unack":
            transition_name = "rtn_unack_to_normal"
        else:
            return False
        self.__timestamp = now
        self.__transition(transition_name=transition_name)
        return True

    def _acknowledge_in_memory(self, now:datetime)->bool:
        r"""Acknowledge without per-alarm DB writes or socket emits."""
        self._defer_persist = True
        try:
            return self._apply_acknowledge(now)
        finally:
            self._defer_persist = False

    @logging_error_handler
    @set_event(message="Alarm acknowledged", classification="Control", priority=2, criticity=3)
    def acknowledge(self, user:User=None, operator_id:int=None):
        r"""
        Acknowledges the alarm.

        **Parameters:**

        * **user** (User, optional): User performing the acknowledgment.
        """
        from ..timebase import quantize_datetime_ms

        current = (getattr(self.current_state, "name", None) or "").lower()
        if current not in ("unack_alarm", "rtn_unack"):
            logging.getLogger("pyautomation").debug(
                "ALM.ACK.Noop state=%s alarm=%s",
                current,
                self.name,
            )
            return False
        now = quantize_datetime_ms(datetime.now(timezone.utc))
        self._pending_operator_id = self._operator_pk(user=user, operator_id=operator_id)
        if not self._apply_acknowledge(now):
            self._pending_operator_id = None
            return False
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm shelved", classification="Control", priority=2, criticity=3)
    def shelve(self, user:User=None, **options):
        r"""
        Temporarily suppresses the alarm (Shelving).

        **Parameters:**

        * **options**: Time duration arguments (days, hours, minutes, seconds).
        """
        options_time = {key: options[key] if key in options else self._shelved_options_time[key] for key in self._shelved_options_time}
        
        if options_time!=self._shelved_options_time:
            
            self._shelved_time = datetime.now(timezone.utc)
            self._shelved_until = self._shelved_time + timedelta(**options_time)

        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_shelved'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm unshelved", classification="Control", priority=2, criticity=3)
    def unshelve(self, user:User=None, current_value=None):
        r"""
        Manually un-shelves the alarm, returning it to service.
        After unshelving, re-evaluates the current tag value to determine the correct state.
        
        **Parameters:**
        
        * **user** (User, optional): User performing the unshelve action.
        * **current_value** (Quantity, optional): Current tag value. If not provided, will be obtained from the tag.
        """
        self.__return_to_service()
        # Re-evaluate the alarm condition with current tag value after unshelving
        if current_value is None:
            current_value = self.tag.value
        if current_value:
            self.update(current_value)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm suppressed", classification="Control", priority=2, criticity=3)
    def designed_suppression(self, user:User=None):
        r"""
        Suppresses the alarm by design (e.g., maintenance mode).
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_suppressed_by_design'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm unsuppressed", classification="Control", priority=2, criticity=3)
    def designed_unsuppression(self, user:User=None):
        r"""
        Removes designed suppression.
        """
        self.__return_to_service()
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm removed from service", classification="Control", priority=2, criticity=3)
    def remove_from_service(self, user:User=None):
        r"""
        Takes the alarm out of service entirely.
        """
        current_state = self.current_state.name.lower()
        transition_name = f'{current_state}_to_out_of_service'
        self.__transition(transition_name=transition_name)
        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    @set_event(message="Alarm returned to service", classification="Control", priority=2, criticity=3)
    def return_to_service(self, user:User=None):
        r"""
        Returns the alarm to service from 'Out of Service'.
        """
        self.__return_to_service()

        return self, f"{self.tag.get_name()}"

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        observer = AlarmTagObserver(machine)
        self._machine_observer = observer
        query = dict()
        query["action"] = "attach_observer"
        query["parameters"] = {
            "name": tag.name,
            "observer": observer,
        }
        self.tag_engine.request(query)
        self.tag_engine.response()

    @logging_error_handler
    def detach_from_tag(self):
        observer = getattr(self, "_machine_observer", None)
        tag = getattr(self, "tag", None)
        if observer is None or tag is None:
            return
        tag_name = tag.name if hasattr(tag, "name") else None
        if tag_name:
            try:
                self.tag_engine.detach(name=tag_name, observer=observer)
            except Exception:
                try:
                    tag.detach(observer)
                except Exception:
                    pass
        self._machine_observer = None

    @set_event(message="Alarm updated", classification="Configuration", priority=2, criticity=3)
    def put(
            self, 
            user:User=None,
            name:str=None,
            tag:str=None,
            description:str=None,
            alarm_type:TriggerType=None,
            trigger_value:float=None,
            on_delay:float=None,
            off_delay:float=None,
            on_delay_units:str=None,
            off_delay_units:str=None):
        r"""
        Updates the alarm configuration.

        **Parameters:**
        
        * **name** (str): Alarm name.
        * **tag** (str): Tag bound to alarm.
        * **description** (str): Alarm description.
        * **alarm_type** (TriggerType): Alarm type ['HIGH-HIGH', 'HIGH', 'LOW', 'LOW-LOW', 'BOOL'].
        * **trigger_value** (float): Alarm trigger value.

        **Returns:**

        * **tuple**: (Alarm instance, status message)
        """
        message = ""
        if alarm_type:

            if alarm_type.value.upper() in ["HIGH-HIGH", "HIGH", "LOW", "LOW-LOW", "BOOL"]:

                self.alarm_setpoint.type = alarm_type

                message += f" alarm_type: {alarm_type.value}"

        if trigger_value is not None:
            self.alarm_setpoint.value = trigger_value
            message += f" trigger value: {trigger_value}"
        
        if name:

            self._name = name
            message += f" name: {name}"

        if tag:
            if isinstance(tag, str):
                resolved = self.tag_engine.get_tag_by_name(name=tag)
                if resolved is None:
                    return self, f"Tag '{tag}' does not exist"
                tag = resolved
            current = getattr(self, "tag", None)
            current_name = getattr(current, "name", None) or (current if isinstance(current, str) else "")
            new_name = getattr(tag, "name", "")
            if current_name != new_name:
                try:
                    self.detach_from_tag()
                except Exception:
                    pass
                self.tag = tag
                self.attach(machine=self, tag=tag)
            message += f" tag: {new_name}"

        if description:

            self._description = description
            message += f" description: {description}"

        delay_changed = False
        if on_delay is not None:
            self.alarm_on_delay = FloatType(clamp_alarm_delay(on_delay, default=self._on_delay_s()))
            message += f" on_delay: {self._on_delay_s()}"
            delay_changed = True
        if off_delay is not None:
            self.alarm_off_delay = FloatType(clamp_alarm_delay(off_delay, default=self._off_delay_s()))
            message += f" off_delay: {self._off_delay_s()}"
            delay_changed = True
        if on_delay_units is not None:
            self.on_delay_units = normalize_delay_units(on_delay_units)
        if off_delay_units is not None:
            self.off_delay_units = normalize_delay_units(off_delay_units)
        if delay_changed:
            self._reset_delay_timers()
            try:
                value = getattr(self.tag, "value", None)
                if value is not None:
                    ts = getattr(self.tag, "timestamp", None) or datetime.now(timezone.utc)
                    self.notify(tag=self.tag.name, value=value, timestamp=ts)
            except Exception:
                pass

        return self, message

    def _get_active_transitions(self):
        r"""
        Gets allowed transitions based on the current state.

        **Returns:**

        * **list**: List of available transitions.
        """
        result = list()

        current_state = self.current_state
        transitions = self.transitions

        for transition in transitions:

            if transition.source == current_state:

                result.append(transition)

        return result
    
    @logging_error_handler
    def __transition(self, transition_name:str):

        allowed_transitions = self._get_active_transitions()
        for _transition in allowed_transitions:
            
            if f"{_transition.source.name}_to_{_transition.target.name}"==transition_name:
                
                self.send(transition_name)

    @logging_error_handler
    def __return_to_service(self):

        current_state = self.current_state.name.lower()

        if self.state.alarm_status.lower()=="active":

            transition_name = f'{current_state}_to_unack_alarm'

        else:

            transition_name = f'{current_state}_to_normal'
        
        self.__transition(transition_name=transition_name)

    @logging_error_handler
    def get_operator_actions(self)->list:
        r"""
        Returns a list of available actions for the operator based on current state.

        **Returns:**

        * **dict**: Map of Action Name -> Action Method.
        """
        current_state = self.current_state.name.lower()
            
        if current_state in ("unack_alarm", "rtn_unack"):

            result = {
                "Acknowledge": "acknowledge",
                "Shelve": "shelve",
                "Designed Suppression": "designed_suppression",
                "Remove From Service": "remove_from_service"
            }

        elif current_state=="shelved":

            result = {
                "Unshelve": "unshelve"
            }

        elif current_state=="suppressed_by_design":

            result = {
                "Designed Unsuppression": "designed_unsuppression"
            }

        elif current_state=="out_of_service":

            result = {
                "Return To Service": "return_to_service"
            }

        else:

            result = {
                "Shelve": "shelve",
                "Designed Suppression": "designed_suppression",
                "Remove From Service": "remove_from_service"
            }

        return result

    def serialize(self):
        r"""
        Serializes the alarm object to a JSON-compatible dictionary.

        **Returns:**

        * **dict**: Alarm data including state, setpoint, and metadata.
        """
        from ..timebase import iso_millis

        timestamp = iso_millis(self.timestamp)
        ack_timestamp = iso_millis(self.ack_timestamp)

        setpoint = self.alarm_setpoint.serialize()
        return {
            "identifier": self.identifier,
            "segment": self.segment,
            "manufacturer": self.manufacturer,
            "timestamp": timestamp,
            "last_transition_ts": iso_millis(getattr(self, "last_transition_ts", None)),
            "last_transition_from": getattr(self, "last_transition_from", None),
            "last_transition_to": getattr(self, "last_transition_to", None),
            "name": self.name,
            "display_name": getattr(self, "display_name", None),
            "tag": self.tag.name,
            "state": self.state.serialize(),
            "alarm_type": setpoint.get("type"),
            "trigger_value": setpoint.get("value"),
            "alarm_setpoint": setpoint,
            "ack_timestamp": ack_timestamp,
            "description": self.description,
            "actions": self.get_operator_actions(),
            "on_delay": self._on_delay_s(),
            "off_delay": self._off_delay_s(),
            "on_delay_units": self.on_delay_units,
            "off_delay_units": self.off_delay_units,
            "condition_met": bool(self._condition_met),
            "on_timer_remaining": self._timer_remaining(self._on_timer_start, self._on_delay_s())
            if self._delay_phase() == "pending"
            else None,
            "off_timer_remaining": self._timer_remaining(self._off_timer_start, self._off_delay_s())
            if self._delay_phase() == "clearing"
            else None,
            "delay_phase": self._delay_phase(),
        }
