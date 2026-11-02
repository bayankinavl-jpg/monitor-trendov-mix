"""Локальный пульт монитора: лендинг с кнопкой запуска парсера.

python scripts/monitor_server.py [--port 8765]

Пересобирает и открывает data/exports/report_artifact.html по адресу http://127.0.0.1:8765
и добавляет под заголовком панель: поле «за сколько дней» и кнопку запуска.
Кнопка запускает run.sh в фоне, панель показывает вывод парсера.
Сервер слушает только 127.0.0.1, поэтому снаружи компьютера он недоступен.
Одновременно идёт не больше одного запуска."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from registry.db import get_connection
from scripts.build_landing import build as build_landing

LANDING_PATH = config.EXPORTS_DIR / "report_artifact.html"
RUN_SCRIPT = config.BASE_DIR / "run.sh"
LOG_TAIL_LINES = 200

PANEL = """
<style>
.run-panel { max-width: 920px; margin: 0 auto 22px; background: var(--surface); border: 1px solid var(--line);
  border-radius: 10px; padding: 14px 18px; display: grid; gap: 10px; }
.run-panel h2 { margin: 0; font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
.run-row { display: flex; gap: 10px 14px; align-items: center; flex-wrap: wrap; }
.run-row input { width: 84px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px;
  background: var(--bg); color: var(--ink); font: inherit; }
.run-row button { padding: 8px 18px; border: 1px solid var(--accent); border-radius: 8px;
  background: var(--accent); color: var(--surface); font: 600 0.9rem var(--font-body); cursor: pointer; }
.run-row button:disabled { opacity: 0.55; cursor: default; }
.run-status { color: var(--muted); font-size: 0.85rem; margin: 0; }
.run-log { max-height: 280px; overflow: auto; margin: 0; padding: 10px 12px; background: var(--surface-2);
  border-radius: 8px; font: 0.75rem/1.5 var(--font-data); white-space: pre-wrap; }
</style>
<div class="run-panel">
  <h2>Запуск парсера</h2>
  <div class="run-row">
    <label for="run-days">За сколько дней</label>
    <input id="run-days" type="number" min="1" max="365" placeholder="авто">
    <button id="run-btn" type="button">Запустить парсер</button>
    <span class="run-status" id="run-status"></span>
  </div>
  <p class="run-status">Пусто — столько дней, сколько прошло с прошлого запуска. После успешного сбора страница обновится сама.</p>
  <pre class="run-log" id="run-log" hidden></pre>
</div>
<script>
(() => {
  const btn = document.getElementById("run-btn");
  const days = document.getElementById("run-days");
  const status = document.getElementById("run-status");
  const log = document.getElementById("run-log");
  let timer = null;
  let wasRunning = false;

  function render(s) {
    btn.disabled = s.running;
    if (s.running) status.textContent = "Идёт сбор с " + s.started_at + "…";
    else if (s.exit_code === null) status.textContent = "";
    else if (s.exit_code === 0) status.textContent = "Готово: " + s.finished_at;
    else status.textContent = "Ошибка, код " + s.exit_code + " (" + s.finished_at + ")";
    if (s.log) { log.hidden = false; log.textContent = s.log; log.scrollTop = log.scrollHeight; }
    if (s.running && !timer) { timer = setInterval(poll, 2000); wasRunning = true; }
    if (!s.running && timer) { clearInterval(timer); timer = null; }
    if (!s.running && wasRunning && s.exit_code === 0) setTimeout(() => location.reload(), 1200);
  }
  async function poll() {
    try { render(await (await fetch("/status")).json()); }
    catch (e) { status.textContent = "Нет связи с сервером пульта"; }
  }
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    const resp = await fetch("/run", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days: days.value ? Number(days.value) : null }) });
    const s = await resp.json();
    if (!resp.ok) status.textContent = s.error;
    render(s.state || s);
  });
  poll();
})();
</script>
"""


class RunState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.exit_code: int | None = None
        self.lines: list[str] = []

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "log": "".join(self.lines[-LOG_TAIL_LINES:]),
            }

    def start(self, days: int | None) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.started_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            self.finished_at = None
            self.exit_code = None
            self.lines = []
        cmd = [str(RUN_SCRIPT)] + (["--days", str(days)] if days else [])
        threading.Thread(target=self._run, args=(cmd,), daemon=True).start()
        return True

    def _run(self, cmd: list[str]) -> None:
        try:
            proc = subprocess.Popen(
                cmd, cwd=config.BASE_DIR, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            for line in proc.stdout:
                with self.lock:
                    self.lines.append(line)
            code = proc.wait()
        except OSError as exc:
            with self.lock:
                self.lines.append(f"Не удалось запустить {cmd[0]}: {exc}\n")
            code = -1
        with self.lock:
            self.running = False
            self.exit_code = code
            self.finished_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")


STATE = RunState()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, data: dict) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path == "/":
            self._rebuild_landing()
            html = LANDING_PATH.read_text(encoding="utf-8")
            html = html.replace("</header>", "</header>" + PANEL, 1)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/status":
            self._json(200, STATE.snapshot())
        else:
            self._send(404, b"not found", "text/plain")

    def _rebuild_landing(self) -> None:
        """Пересобирает страницу из реестра; если не вышло, отдаётся прежний файл."""
        try:
            conn = get_connection(config.MAIN_DB_PATH)
            try:
                build_landing(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 - пульт должен открыться при любой ошибке сборки
            print(f"Страницу не удалось пересобрать: {exc}")

    def do_POST(self) -> None:
        # Запрос с чужой страницы в браузере придёт с другим Origin — отклоняем.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in (f"http://{host}",):
            self._json(403, {"error": "запуск разрешён только со страницы пульта"})
            return
        if self.path != "/run":
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            days = json.loads(self.rfile.read(length) or b"{}").get("days")
            if days is not None and not (isinstance(days, int) and 1 <= days <= 365):
                raise ValueError
        except ValueError:
            self._json(400, {"error": "число дней — от 1 до 365"})
            return
        if not STATE.start(days):
            self._json(409, {"error": "парсер уже запущен", "state": STATE.snapshot()})
            return
        self._json(200, STATE.snapshot())

    def log_message(self, format: str, *args) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный пульт монитора с запуском парсера")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Пульт монитора: http://127.0.0.1:{args.port}  (остановить — Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
