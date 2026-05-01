import asyncio
import logging
import sys

from nabcommon.nabservice import NabService


class NabPlannerD(NabService):
    def __init__(self):
        super().__init__()
        self.loop_cv = asyncio.Condition()

    async def reload_config(self):
        async with self.loop_cv:
            self.loop_cv.notify()

    def start_service_loop(self, loop):
        return loop.create_task(self.service_loop())

    async def stop_service_loop(self):
        async with self.loop_cv:
            self.running = False
            self.loop_cv.notify()

    async def service_loop(self):
        async with self.loop_cv:
            while self.running:
                try:
                    from .scheduler import run_due_rules

                    await run_due_rules()
                except Exception as err:
                    logging.error(f"planner loop failed: {err}")
                try:
                    await asyncio.wait_for(self.loop_cv.wait(), 30)
                except asyncio.TimeoutError:
                    pass


if __name__ == "__main__":
    NabPlannerD.main(sys.argv[1:])
