import os
import json
import sqlite3
import datetime
import time
import re
import difflib
from typing import Dict, List, Optional, Tuple, Any

ANTIGRAVITY_DIR = os.path.expanduser(r"~\.gemini\antigravity")
DB_PATH = os.path.join(ANTIGRAVITY_DIR, "conversation_summaries.db")
BRAIN_DIR = os.path.join(ANTIGRAVITY_DIR, "brain")

class TaskEvent:
    def __init__(
        self,
        step_index: int,
        category: str,
        text: str,
        detail: str = "",
        timestamp: str = "",
        command_str: str = "",
        response_str: str = "",
        lines_added: Optional[int] = None,
        lines_removed: Optional[int] = None,
        applied: bool = False
    ):
        self.step_index = step_index
        self.category = category  # 'command', 'read', 'edit', 'write', 'search', 'mcp', 'user', 'other'
        self.text = text
        self.detail = detail
        self.timestamp = timestamp
        self.command_str = command_str
        self.response_str = response_str
        self.lines_added = lines_added
        self.lines_removed = lines_removed
        self.applied = applied

        # Internal helper attributes for diff calculation
        self._raw_target: str = ""
        self._raw_replacement: str = ""
        self._raw_line_count: int = 0
        self._was_truncated: bool = False

    def to_dict(self):
        return {
            "step_index": self.step_index,
            "category": self.category,
            "text": self.text,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "command_str": self.command_str,
            "response_str": self.response_str,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "applied": self.applied,
        }


class AntigravityMonitor:
    def __init__(self):
        self.current_conv_id: Optional[str] = None
        self.current_title: str = "Tidak Ada Sesi Aktif"
        self.current_status: str = "IDLE"  # RUNNING or IDLE
        self.file_offset: int = 0
        self.events: List[TaskEvent] = []
        self.turn_tool_events: List[TaskEvent] = []
        self.pending_tool_events: List[TaskEvent] = []
        self.recently_updated_events: List[TaskEvent] = []
        self.start_time: Optional[datetime.datetime] = None
        self.current_turn_start_time: Optional[datetime.datetime] = None
        self.last_step_time: Optional[datetime.datetime] = None
        self.active_sessions: List[Tuple[str, str, str]] = []  # [(id, title, status)]

        # Model & Token Quota Tracking
        self.model_name: str = "Gemini 3.8 Flash"
        self.total_tokens_used: int = 0
        self.model_context_limit: int = 1_000_000
        self.remaining_quota_pct: float = 100.0
        self.is_thinking: bool = False
        self.new_turn_started: bool = False
        self.last_tool_completed_at: float = 0.0
        self._is_initial_batch: bool = False

        # Background Process Tracking (PowerShell, tasks, etc.)
        self.background_tasks: Dict[str, Dict] = {}
        self.dismissed_task_ids: set = set()
        self._last_invoked_command: Dict[str, str] = {}

        # User Decision / Input Needed Tracking
        self.pending_user_decision: Optional[Dict[str, Any]] = None

        # Completion Summary Tracking
        self.last_completion_summary: str = ""

    def get_all_sessions(self) -> List[Tuple[str, str, str, bool]]:
        """
        Mengambil daftar sesi terbaru dari conversation_summaries.db.
        Mengembalikan list tuple: (conversation_id, title, status, is_running)
        """
        if not os.path.exists(DB_PATH):
            return []

        try:
            uri = f"file:{DB_PATH.replace(os.sep, '/')}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT conversation_id, title, status, not_fully_idle, last_modified_time
                FROM conversation_summaries
                ORDER BY not_fully_idle DESC, last_modified_time DESC
                LIMIT 15
                """
            )
            rows = cursor.fetchall()
            conn.close()

            sessions = []
            for r in rows:
                c_id, title, status, not_fully_idle, _ = r
                title = title.strip() if title else f"Sesi {c_id[:8]}"
                is_running = (not_fully_idle == 1) or ("RUNNING" in (status or "").upper())
                status_str = "RUNNING" if is_running else "IDLE"
                sessions.append((c_id, title, status_str, is_running))
            return sessions
        except Exception:
            return []

    def check_active_session(self, preferred_conv_id: Optional[str] = None) -> Tuple[bool, str, str, str]:
        """
        Cek apakah ada sesi yang sedang berjalan.
        Jika preferred_conv_id diberikan, prioritaskan sesi tersebut jika masih ada.
        Mengembalikan: (is_running, conv_id, title, status)
        """
        sessions = self.get_all_sessions()
        self.active_sessions = [(s[0], s[1], s[2]) for s in sessions]

        if not sessions:
            return False, "", "Tidak Ada Sesi", "IDLE"

        target_session = None

        if preferred_conv_id:
            for s in sessions:
                if s[0] == preferred_conv_id:
                    target_session = s
                    break

        if not target_session:
            for s in sessions:
                if s[3]:  # is_running
                    target_session = s
                    break

        if not target_session:
            target_session = sessions[0]

        conv_id, title, status_str, is_running = target_session

        if conv_id != self.current_conv_id:
            self.current_conv_id = conv_id
            self.file_offset = 0
            self.events = []
            self.turn_tool_events = []
            self.pending_tool_events = []
            self.recently_updated_events = []
            self.is_thinking = False
            self.last_tool_completed_at = 0.0
            self.start_time = None
            self.current_turn_start_time = None
            self.total_tokens_used = 0
            self.remaining_quota_pct = 100.0
            self.background_tasks = {}
            self._last_invoked_command = {}
            self.pending_user_decision = None
            self.last_completion_summary = ""

        self.current_title = title
        self.current_status = status_str

        return is_running, conv_id, title, status_str

    def on_run_started(self):
        """
        Dipanggil saat status sesi berubah menjadi RUNNING.
        Menandai awal mula turn aktif baru.
        """
        self.turn_tool_events = []
        self.pending_tool_events = []
        self.is_thinking = True
        self.last_tool_completed_at = 0.0
        self.pending_user_decision = None
        self.last_completion_summary = ""
        self.current_turn_start_time = datetime.datetime.now(datetime.timezone.utc)

    def poll_transcript(self) -> List[TaskEvent]:
        """
        Membaca data baru dari transcript.jsonl secara streaming.
        """
        self.recently_updated_events = []
        if not self.current_conv_id:
            return []

        transcript_path = os.path.join(
            BRAIN_DIR, self.current_conv_id, ".system_generated", "logs", "transcript.jsonl"
        )

        if not os.path.exists(transcript_path):
            return []

        try:
            current_size = os.path.getsize(transcript_path)
            if current_size < self.file_offset:
                self.file_offset = 0
                self.events = []
                self.turn_tool_events = []
                self.pending_tool_events = []

            if current_size == self.file_offset:
                return []

            self._is_initial_batch = (self.file_offset == 0)
            new_events: List[TaskEvent] = []
            with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.file_offset)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        parsed = self._parse_transcript_line(data)
                        if parsed:
                            new_events.extend(parsed)
                    except Exception:
                        pass
                self.file_offset = f.tell()

            self._is_initial_batch = False
            if new_events:
                self.events.extend(new_events)
            return new_events

        except Exception:
            self._is_initial_batch = False
            return []

    @staticmethod
    def _clean_arg_str(val: Any) -> str:
        if not isinstance(val, str):
            return ""
        s = val.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            try:
                return json.loads(s)
            except Exception:
                return s.strip('"\'')
        return s.strip('"\'')

    @staticmethod
    def _compute_fallback_diff(target: str, replacement: str) -> Tuple[int, int]:
        if not target and not replacement:
            return 0, 0
        t_lines = target.splitlines() if target else []
        r_lines = replacement.splitlines() if replacement else []
        matcher = difflib.SequenceMatcher(None, t_lines, r_lines)
        added = 0
        removed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                removed += (i2 - i1)
                added += (j2 - j1)
            elif tag == "delete":
                removed += (i2 - i1)
            elif tag == "insert":
                added += (j2 - j1)
        return added, removed

    @staticmethod
    def _extract_command_response(content: str, status_val: str) -> str:
        if not content or not isinstance(content, str):
            return ""

        if "Command output:" in content:
            out_part = content.split("Command output:", 1)[1].strip()
            if out_part:
                lines = [ln.strip() for ln in out_part.splitlines() if ln.strip()]
                if lines:
                    joined = " | ".join(lines[:4])
                    if len(joined) > 220:
                        joined = joined[:217] + "..."
                    return joined

        if "No output from the command." in content:
            m_code = re.search(r"Command exited with code\s+(\d+)", content)
            code = m_code.group(1) if m_code else "0"
            return f"Exit code {code} (Selesai tanpa output teks)"

        if "Tool is running as a background task" in content:
            return "Berjalan di latar belakang (Background Task)"

        if status_val == "ERROR" or "Encountered error" in content:
            lines = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith(("Created At:", "Completed At:"))]
            if lines:
                return lines[0][:200]

        return ""

    def _parse_transcript_line(self, data: dict) -> List[TaskEvent]:
        events = []
        step_idx = data.get("step_index", 0)
        created_at = data.get("created_at", "")
        msg_type = data.get("type", "")
        status_val = data.get("status", "")
        truncated_fields = data.get("truncated_fields") or []

        dt_created = None
        if created_at:
            try:
                dt_str = created_at.replace("Z", "+00:00")
                dt_created = datetime.datetime.fromisoformat(dt_str)
                self.last_step_time = dt_created
                if not self.start_time:
                    self.start_time = dt_created
            except Exception:
                pass

        # Update Model Token Quota from PLANNER_RESPONSE
        if msg_type == "PLANNER_RESPONSE":
            inp = data.get("input_tokens", 0) or 0
            cache = data.get("cache_read_tokens", 0) or 0
            out = data.get("output_tokens", 0) or 0
            current_turn_tokens = inp + cache + out
            if current_turn_tokens > 0:
                self.total_tokens_used = current_turn_tokens
                self._calculate_quota_percentage()

            tool_calls = data.get("tool_calls", [])
            if tool_calls:
                self.is_thinking = False
            else:
                self.pending_tool_events = []
                self.is_thinking = True

            # Ekstraksi ringkasan implementasi / perbaikan
            resp_content = data.get("content", "")
            if resp_content:
                clean_sum = self._extract_clean_summary(resp_content)
                if clean_sum:
                    self.last_completion_summary = clean_sum

        # Parse tool calls
        tool_calls = data.get("tool_calls", [])
        if tool_calls:
            # Jika ada tool call baru dan bukan ask_question lagi, bersihkan pending decision
            if self.pending_user_decision and step_idx > self.pending_user_decision.get("step_index", 0):
                if not any(tc.get("name") == "ask_question" for tc in tool_calls):
                    self.pending_user_decision = None

            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {})

                summary = self._clean_arg_str(args.get("toolSummary", ""))
                cmd = self._clean_arg_str(args.get("CommandLine", ""))
                path = self._clean_arg_str(args.get("Path", ""))
                base_name = os.path.basename(path) if path else ""

                if name == "ask_question":
                    questions = args.get("questions", [])
                    q_title = ""
                    detail_str = ""
                    if isinstance(questions, list) and questions:
                        q_item = questions[0]
                        if isinstance(q_item, dict):
                            q_title = q_item.get("question", "")
                            opts = q_item.get("options", [])
                            if opts and isinstance(opts, list):
                                detail_str = "Pilihan: " + ", ".join(str(o) for o in opts)
                    elif isinstance(questions, dict):
                        q_title = questions.get("question", "")

                    if not q_title:
                        q_title = args.get("question", "") or "Pilihan keputusan diperlukan"

                    label = f"Membutuhkan input user: {q_title}"
                    ev = TaskEvent(step_idx, "decision", label, detail_str or q_title, created_at)
                    events.append(ev)
                    self.pending_user_decision = {
                        "type": "ask_question",
                        "title": q_title,
                        "detail": detail_str,
                        "step_index": step_idx,
                        "created_at": created_at
                    }

                elif name == "run_command":
                    label = f"Ran {summary}" if summary else f"Ran {cmd[:40]}"
                    ev = TaskEvent(
                        step_idx,
                        "command",
                        label,
                        cmd,
                        created_at,
                        command_str=cmd
                    )
                    events.append(ev)
                    self._last_invoked_command = {"cmd": cmd, "summary": summary}

                elif name == "read_file":
                    sl = self._clean_arg_str(str(args.get("StartLine", "")))
                    el = self._clean_arg_str(str(args.get("EndLine", "")))
                    line_info = f" #L{sl}-{el}" if sl and el else ""
                    ext = os.path.splitext(base_name)[1].lstrip(".").upper()
                    ext_tag = f"[{ext}] " if ext else ""
                    label = f"Analyzed {ext_tag}{base_name}{line_info}"
                    ev = TaskEvent(step_idx, "read", label, path, created_at)
                    events.append(ev)

                elif name == "edit_file":
                    meta = args.get("ArtifactMetadata", {})
                    if isinstance(meta, dict) and meta.get("RequestFeedback") is True:
                        s_sum = meta.get("Summary", "").strip()
                        first_line = s_sum.split("\n")[0].strip() if s_sum else "Tinjau rencana implementasi"
                        label = f"Membutuhkan input user: {first_line}"
                        ev = TaskEvent(step_idx, "decision", label, s_sum, created_at)
                        events.append(ev)
                        self.pending_user_decision = {
                            "type": "plan_feedback",
                            "title": first_line,
                            "detail": s_sum,
                            "step_index": step_idx,
                            "created_at": created_at
                        }
                    else:
                        label = f"Edited {base_name}"
                        ev = TaskEvent(step_idx, "edit", label, path, created_at)
                        ev._raw_target = self._clean_arg_str(args.get("Target", ""))
                        ev._raw_replacement = self._clean_arg_str(args.get("Replacement", ""))
                        ev._was_truncated = ("tool_calls" in truncated_fields)
                        events.append(ev)

                elif name == "write_file":
                    meta = args.get("ArtifactMetadata", {})
                    if isinstance(meta, dict) and meta.get("RequestFeedback") is True:
                        s_sum = meta.get("Summary", "").strip()
                        first_line = s_sum.split("\n")[0].strip() if s_sum else "Tinjau rencana implementasi"
                        label = f"Membutuhkan input user: {first_line}"
                        ev = TaskEvent(step_idx, "decision", label, s_sum, created_at)
                        events.append(ev)
                        self.pending_user_decision = {
                            "type": "plan_feedback",
                            "title": first_line,
                            "detail": s_sum,
                            "step_index": step_idx,
                            "created_at": created_at
                        }
                    else:
                        label = f"Created {base_name}"
                        ev = TaskEvent(step_idx, "write", label, path, created_at)
                        raw_content = self._clean_arg_str(args.get("Content", ""))
                        ev._raw_line_count = len(raw_content.splitlines()) if raw_content else 0
                        ev._was_truncated = ("tool_calls" in truncated_fields)
                        events.append(ev)

                elif name == "search_web":
                    q = self._clean_arg_str(args.get("query", ""))
                    label = f"Web Search: {q[:35]}"
                    ev = TaskEvent(step_idx, "search", label, q, created_at)
                    events.append(ev)

                elif name == "invoke_subagent":
                    role = self._clean_arg_str(args.get("Role", "")) or self._clean_arg_str(args.get("TypeName", ""))
                    label = f"Subagent: {role}" if role else "Subagent invoked"
                    ev = TaskEvent(step_idx, "other", label, str(args), created_at)
                    events.append(ev)

                elif name == "manage_task":
                    act = self._clean_arg_str(args.get("Action", ""))
                    tid = self._clean_arg_str(args.get("TaskId", "")).split("/")[-1]
                    if act in ("kill", "kill_all"):
                        if tid:
                            self.background_tasks.pop(tid, None)
                        if act == "kill_all":
                            self.background_tasks.clear()
                    label = f"Task: {act} {tid}" if tid else f"Task: {act}"
                    ev = TaskEvent(step_idx, "other", label, str(args), created_at)
                    events.append(ev)

                elif "mcp" in name:
                    label = f"MCP: {name}"
                    ev = TaskEvent(step_idx, "mcp", label, str(args), created_at)
                    events.append(ev)

                else:
                    label = f"Action: {name}"
                    ev = TaskEvent(step_idx, "other", label, str(args), created_at)
                    events.append(ev)

            if events:
                self.turn_tool_events.extend(events)
                self.pending_tool_events.extend(events)
                self.is_thinking = False
                self.last_tool_completed_at = 0.0

        # 1. USER_INPUT / GENERIC: Menandai awal turn, penyelesaian tool, atau keputusan
        if msg_type == "USER_INPUT":
            if dt_created:
                self.current_turn_start_time = dt_created
            self.turn_tool_events = []
            self.pending_tool_events = []
            self.is_thinking = True
            self.last_tool_completed_at = 0.0
            self.new_turn_started = True
            self.pending_user_decision = None
            self.last_completion_summary = ""

            input_content = data.get("content", "")
            model_match = re.search(
                r"Model Selection[^\w\s]*\s+from\s+.*?to\s+([^\r\n]+?)(?:\.\s|\.$|$)",
                input_content,
                re.IGNORECASE
            )
            if model_match:
                raw_model = model_match.group(1).strip()
                if raw_model and raw_model.lower() != "none":
                    clean_name = re.sub(r"\(.*?\)", "", raw_model).strip(" `'\"")
                    self.model_name = clean_name if clean_name else raw_model
                    self._calculate_quota_percentage()

        elif msg_type == "GENERIC":
            if self.pending_user_decision and step_idx > self.pending_user_decision.get("step_index", 0):
                self.pending_user_decision = None

            gen_content = data.get("content", "") or ""

            # Pasangkan hasil tool (GENERIC) ke pending_tool_events
            if self.pending_tool_events:
                done_ev = self.pending_tool_events.pop(0)

                if done_ev.category == "edit" and status_val == "DONE":
                    matches = re.findall(r"\(\+(\d+)/-(\d+)\s*lines?\)", gen_content)
                    if matches:
                        done_ev.lines_added = sum(int(m[0]) for m in matches)
                        done_ev.lines_removed = sum(int(m[1]) for m in matches)
                        done_ev.applied = True
                    elif not done_ev._was_truncated and (done_ev._raw_target or done_ev._raw_replacement):
                        add_c, rem_c = self._compute_fallback_diff(done_ev._raw_target, done_ev._raw_replacement)
                        done_ev.lines_added = add_c
                        done_ev.lines_removed = rem_c
                        done_ev.applied = True
                    else:
                        done_ev.lines_added = 1
                        done_ev.lines_removed = 1
                        done_ev.applied = True
                    self.recently_updated_events.append(done_ev)

                elif done_ev.category == "write" and status_val == "DONE":
                    line_cnt = done_ev._raw_line_count
                    if (done_ev._was_truncated or line_cnt == 0) and done_ev.detail and os.path.exists(done_ev.detail):
                        try:
                            with open(done_ev.detail, "r", encoding="utf-8", errors="replace") as rf:
                                line_cnt = sum(1 for _ in rf)
                        except Exception:
                            pass
                    done_ev.lines_added = max(1, line_cnt) if line_cnt > 0 else 0
                    done_ev.lines_removed = 0
                    done_ev.applied = True
                    self.recently_updated_events.append(done_ev)

                elif done_ev.category == "command":
                    resp = self._extract_command_response(gen_content, status_val)
                    if resp:
                        done_ev.response_str = resp
                    done_ev.applied = (status_val in ("DONE", "RUNNING"))
                    self.recently_updated_events.append(done_ev)

                else:
                    done_ev.applied = (status_val == "DONE")

                # Jika seluruh tool pada PLANNER_RESPONSE terakhir sudah selesai dieksekusi,
                # maka fase berikutnya selama sesi masih RUNNING adalah THINKING untuk langkah selanjutnya!
                if len(self.pending_tool_events) == 0:
                    self.is_thinking = True
                    if not self._is_initial_batch:
                        self.last_tool_completed_at = time.time()

        # 2. Deteksi status background tasks dari output / pesan sistem (apapun msg_type nya)
        content = data.get("content", "")
        if content:
            content_lower = content.lower()
            if status_val == "RUNNING" and "tool is running as a background task with task id:" in content_lower:
                m_start = re.search(r"Tool is running as a background task with task id:\s*(\S+)", content, re.IGNORECASE)
                if m_start:
                    full_tid = m_start.group(1).strip()
                    tid = full_tid.split("/")[-1]
                    if tid not in self.dismissed_task_ids:
                        m_desc = re.search(r"Task Description:\s*([^\r\n]+)", content, re.IGNORECASE)
                        cmd = m_desc.group(1).strip() if m_desc else self._last_invoked_command.get("cmd", "")
                        summary = self._last_invoked_command.get("summary", "")

                        cmd_lower = cmd.lower()
                        if "powershell" in cmd_lower or "pwsh" in cmd_lower:
                            proc_name = "PowerShell"
                        elif "python" in cmd_lower:
                            proc_name = "Python"
                        elif "node" in cmd_lower or "npm" in cmd_lower or "yarn" in cmd_lower:
                            proc_name = "Node"
                        elif "git" in cmd_lower:
                            proc_name = "Git"
                        elif "cmd" in cmd_lower or "bat" in cmd_lower:
                            proc_name = "CMD"
                        else:
                            proc_name = "Process"

                        self.background_tasks[tid] = {
                            "task_id": tid,
                            "full_id": full_tid,
                            "proc_name": proc_name,
                            "summary": summary,
                            "command": cmd,
                            "created_at": created_at
                        }

            # Deteksi pembatalan atau penyelesaian task (Semua variasi kata)
            cancel_keywords = [
                "was canceled", "was cancelled", "was completed", "completed with",
                "cancelled", "canceled", "task execution was canceled",
                "tool execution was canceled", "was killed", "terminated", "completed"
            ]
            if any(k in content_lower for k in cancel_keywords):
                found_tids = re.findall(r"task-\d+", content_lower)
                for tid in found_tids:
                    self.background_tasks.pop(tid, None)
                for tid in list(self.background_tasks.keys()):
                    if tid.lower() in content_lower:
                        self.background_tasks.pop(tid, None)

        return events

    def _calculate_quota_percentage(self):
        m_lower = self.model_name.lower()
        if "claude" in m_lower:
            self.model_context_limit = 200_000
        elif "gpt" in m_lower:
            self.model_context_limit = 128_000
        else:
            self.model_context_limit = 1_000_000

        used = self.total_tokens_used
        self.remaining_quota_pct = max(0.0, min(100.0, 100.0 - (used / self.model_context_limit * 100.0)))

    def get_quota_info(self) -> Tuple[float, int, int, str]:
        return self.remaining_quota_pct, self.total_tokens_used, self.model_context_limit, self.model_name

    def get_active_duration_string(self, is_currently_running: bool) -> str:
        """
        Menghitung durasi task AKTIF (hanya saat proses aktif berjalan, bukan seluruh sesi).
        """
        if not self.current_turn_start_time:
            return ""

        now = datetime.datetime.now(datetime.timezone.utc)
        start = self.current_turn_start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=datetime.timezone.utc)

        if is_currently_running:
            delta = now - start
        elif self.last_step_time:
            last = self.last_step_time
            if last.tzinfo is None:
                last = last.replace(tzinfo=datetime.timezone.utc)
            if last >= start:
                delta = last - start
            else:
                delta = datetime.timedelta(seconds=0)
        else:
            delta = datetime.timedelta(seconds=0)

        total_seconds = max(0, int(delta.total_seconds()))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_current_task_event(self) -> Optional[TaskEvent]:
        """
        Mengembalikan tool task event yang sedang dieksekusi pada turn saat ini,
        atau task event terakhir jika ada.
        """
        if self.pending_tool_events:
            return self.pending_tool_events[0]
        if self.turn_tool_events:
            return self.turn_tool_events[-1]
        for ev in reversed(self.events):
            if ev.category != "user":
                return ev
        return None

    def get_last_tool_event(self) -> Optional[TaskEvent]:
        """
        Mengembalikan tool task event terakhir dari sesi.
        """
        for ev in reversed(self.events):
            if ev.category != "user":
                return ev
        if self.turn_tool_events:
            return self.turn_tool_events[-1]
        return None

    def is_agent_thinking(self, is_running: bool) -> bool:
        """
        Mendeteksi secara dinamis apakah saat ini agen sedang dalam fase thinking:
        1. Sesi berstatus RUNNING dan tidak sedang menunggu input keputusan user.
        2. Tidak ada tool yang sedang aktif menunggu penyelesaian (pending_tool_events kosong).
        3. Baik di awal turn maupun di sela antar eksekusi tool ketika model sedang berpikir
           untuk langkah berikutnya (setelah jeda tampil tool singkat 1.15 detik).
        """
        if not is_running:
            return False
        if self.pending_user_decision:
            return False
        if len(self.pending_tool_events) > 0:
            return False
        if not self.is_thinking:
            return False
        if self.last_tool_completed_at > 0 and (time.time() - self.last_tool_completed_at) < 1.15:
            return False
        return True

    def dismiss_background_task(self, task_id: Optional[str] = None):
        """
        Menutup / mengabaikan tugas latar belakang secara manual oleh user.
        """
        if task_id:
            self.dismissed_task_ids.add(task_id)
            self.background_tasks.pop(task_id, None)
        else:
            for tid in list(self.background_tasks.keys()):
                self.dismissed_task_ids.add(tid)
            self.background_tasks.clear()

    def get_background_process_info(self) -> Optional[Dict[str, str]]:
        """
        Mengembalikan informasi proses latar belakang (background task) yang sedang aktif, jika ada.
        """
        for tid in list(self.background_tasks.keys()):
            if tid in self.dismissed_task_ids:
                self.background_tasks.pop(tid, None)

        if not self.background_tasks:
            return None

        latest = list(self.background_tasks.values())[-1]
        proc = latest.get("proc_name", "Process")
        summary = latest.get("summary", "")
        cmd = latest.get("command", "")
        tid = latest.get("task_id", "")

        if summary:
            display = f"Background: {proc} ({summary})"
        elif cmd:
            display = f"Background: {proc} ({cmd[:35]}...)"
        else:
            display = f"Background: {proc} ({tid})"

        return {
            "proc_name": proc,
            "summary": summary,
            "command": cmd,
            "task_id": tid,
            "display_text": display
        }

    def get_pending_decision_info(self) -> Optional[Dict[str, Any]]:
        """
        Mengembalikan informasi keputusan yang sedang membutuhkan input user, jika ada.
        """
        return self.pending_user_decision

    def _extract_clean_summary(self, content: str) -> str:
        """
        Mengekstrak kalimat ringkasan singkat dari respon assistant (PLANNER_RESPONSE).
        Membersihkan blok kode, formatting markdown (#, **, *, `, []),
        dan mengambil intisari kalimat pertama yang bermakna.
        """
        try:
            if not content or not isinstance(content, str):
                return ""

            # 1. Hapus kode blok ```...```
            cleaned = re.sub(r"```[\s\S]*?```", "", content)

            lines = cleaned.strip().split("\n")
            for line in lines:
                line = line.strip()
                if not line or line.startswith(("---", "===", "***", "___", ">")):
                    continue

                clean_line = re.sub(r"^[#\*\-\+\d\.\s]+", "", line).strip()
                clean_line = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean_line)
                clean_line = re.sub(r"\*([^*]+)\*", r"\1", clean_line)
                clean_line = re.sub(r"__([^_]+)__", r"\1", clean_line)
                clean_line = re.sub(r"_([^_]+)_", r"\1", clean_line)
                clean_line = re.sub(r"`([^`]+)`", r"\1", clean_line)
                clean_line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean_line)

                if clean_line.endswith(":"):
                    clean_line = clean_line[:-1].strip()

                if len(clean_line) >= 14:
                    sentences = re.split(r"(?<=[.!?])\s+", clean_line)
                    first_sent = sentences[0].strip()
                    if len(first_sent) >= 14:
                        if len(first_sent) > 135:
                            parts = first_sent[:132].rsplit(" ", 1)
                            first_sent = (parts[0] if parts else first_sent[:132]) + "..."
                        return first_sent

            return ""
        except Exception:
            return ""

    def get_last_completion_summary(self) -> str:
        """
        Mengembalikan ringkasan singkat implementasi / perbaikan task terakhir.
        """
        try:
            if self.last_completion_summary:
                return self.last_completion_summary

            recent_files = []
            for ev in reversed(self.events):
                if ev and ev.category in ("edit", "write") and ev.text:
                    fname = str(ev.text).replace("Edited ", "").replace("Created ", "").strip()
                    if fname and fname not in recent_files:
                        recent_files.append(fname)
                    if len(recent_files) >= 2:
                        break

            if recent_files:
                if len(recent_files) == 1:
                    return f"Perbaikan pada {recent_files[0]}"
                return f"Perbaikan pada {recent_files[0]} & {recent_files[1]}"

            last_ev = self.get_last_tool_event()
            if last_ev and last_ev.text:
                return str(last_ev.text)

            return "Semua instruksi berhasil diselesaikan"
        except Exception:
            return "Semua instruksi berhasil diselesaikan"
