"""Run inside a dedicated Ubuntu VM: sudo /usr/bin/python3 lab/test_mininet.py."""
import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from mininet_agent import Lab


@unittest.skipUnless(os.getuid() == 0, "requires root in the isolated lab VM")
class OpenFlowIntegration(unittest.TestCase):
    def test_topologies(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            controller = subprocess.Popen(
                ["ovs-testcontroller", "-O", "OpenFlow13", f"ptcp:{port}:127.0.0.1",
                 "--unixctl="+str(Path(tmp)/"controller.sock")], stderr=subprocess.DEVNULL
            )
            try:
                for topology, switches, hosts in (("single",1,2),("linear",2,5),("tree",3,4)):
                    with self.subTest(topology=topology):
                        lab = Lab()
                        try:
                            lab.create(dict(topology=topology,switches=switches,hosts=hosts,
                                controller="127.0.0.1",port=port,subnet="10.22.0.0/24"))
                            lab.start()
                            deadline = time.monotonic()+10
                            while True:
                                snap = lab.snapshot()
                                if snap["state"]=="connected" or time.monotonic()>=deadline:
                                    break
                                time.sleep(.25)
                            self.assertEqual(snap["state"],"connected")
                            self.assertEqual(len(snap["switches"]),switches)
                            self.assertEqual(len(snap["hosts"]),hosts)
                            self.assertEqual(len(snap["links"]),switches-1+hosts)
                            reply=lab.dispatch("ping",{"host":"h1","lab_id":lab.id})
                            self.assertIn("2 received",reply["output"])
                            capture=lab.dispatch("capture",{"host":"h1","lab_id":lab.id,"normal_probe":True})
                            self.assertEqual(len(capture["features"]),48)
                            self.assertTrue(any(f["protocol"]==1 for f in capture["observed_flows"]))
                            self.assertGreater(lab.snapshot()["packets"],snap["packets"])
                            if topology=="tree":
                                controller.terminate()
                                controller.wait(timeout=5)
                                deadline=time.monotonic()+8
                                while lab.snapshot()["state"]!="disconnected" and time.monotonic()<deadline:
                                    time.sleep(.25)
                                self.assertEqual(lab.snapshot()["state"],"disconnected")
                        finally:
                            lab.stop()
                            self.assertFalse(lab.dispatch("delete",{})["running"])
            finally:
                controller.terminate()
                controller.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
