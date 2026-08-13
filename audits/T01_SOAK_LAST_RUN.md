# T-01 Soak — last run

- tags=1000 hz=100.0 duration_s=2.0 kill_at_s=1.000
- achieved_tick_hz=7.00
- generated_fsync=7000
- journal_durable=7000
- ring_lag_samples=0
- replicated=7000
- remote_rows_first_pass=7000
- remote_rows_after_retry=7000
- pending_after=0
- exact_once=True
- remote_equals_durable=True

Ring lag is the hardware window of the in-memory flusher (≤ tag_flush_interval_s).
Those samples never reached WAL before SIGKILL; they are the only acceptable loss.
