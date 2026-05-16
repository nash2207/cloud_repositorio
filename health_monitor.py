"""Health monitor for state sync (15s interval)"""
import threading, time, logging
logger = logging.getLogger(__name__)
class HealthMonitor:
    def __init__(self, db, interval=15):
        self.db = db
        self.interval = interval
        self.running = False
        self.thread = None
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Health monitor started (15s interval)")
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    def _monitor_loop(self):
        while self.running:
            try:
                self.db.save()
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
