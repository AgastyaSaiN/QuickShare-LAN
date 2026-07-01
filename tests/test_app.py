import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as quicklan


class QuickLanTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.temp_dir.name)
        self.upload_patch = patch.object(quicklan, "UPLOAD_DIR", self.upload_dir)
        self.pad_patch = patch.object(
            quicklan, "PAD_FILE", self.upload_dir / "shared_pad.txt"
        )
        self.upload_patch.start()
        self.pad_patch.start()
        quicklan.pad_text = ""
        quicklan.app.config.update(TESTING=True)
        self.client = quicklan.app.test_client()

    def tearDown(self):
        self.pad_patch.stop()
        self.upload_patch.stop()
        self.temp_dir.cleanup()

    def test_upload_list_and_download(self):
        response = self.client.post(
            "/api/upload",
            data={"files": (io.BytesIO(b"hello lan"), "hello.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201)

        listed = self.client.get("/api/files").get_json()
        self.assertEqual(listed[0]["name"], "hello.txt")

        download = self.client.get("/files/hello.txt")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, b"hello lan")
        download.close()

    def test_duplicate_names_are_preserved(self):
        for _ in range(2):
            self.client.post(
                "/api/upload",
                data={"files": (io.BytesIO(b"data"), "same.txt")},
                content_type="multipart/form-data",
            )

        names = {item["name"] for item in self.client.get("/api/files").get_json()}
        self.assertEqual(names, {"same.txt", "same (1).txt"})
        download = self.client.get("/files/same%20(1).txt")
        self.assertEqual(download.status_code, 200)
        download.close()

    def test_rejects_missing_files(self):
        response = self.client.post("/api/upload")
        self.assertEqual(response.status_code, 400)

    def test_rejects_download_path_traversal(self):
        response = self.client.get("/files/../app.py")
        self.assertEqual(response.status_code, 404)

    def test_any_client_can_delete_a_shared_file(self):
        shared_file = self.upload_dir / "remove me.txt"
        shared_file.write_text("temporary")

        response = self.client.delete("/api/files/remove%20me.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted"], "remove me.txt")
        self.assertFalse(shared_file.exists())

    def test_delete_rejects_missing_file_and_path_traversal(self):
        self.assertEqual(
            self.client.delete("/api/files/missing.txt").status_code, 404
        )
        self.assertEqual(
            self.client.delete("/api/files/../app.py").status_code, 404
        )

    def test_pad_update_is_broadcast_and_persisted(self):
        first = quicklan.socketio.test_client(quicklan.app)
        second = quicklan.socketio.test_client(quicklan.app)
        first.get_received()
        second.get_received()

        first.emit("pad_update", {"text": "shared from client one"})
        events = second.get_received()

        self.assertEqual(events[0]["name"], "pad_update")
        self.assertEqual(events[0]["args"][0]["text"], "shared from client one")
        self.assertEqual(quicklan.PAD_FILE.read_text(), "shared from client one")
        first.disconnect()
        second.disconnect()


if __name__ == "__main__":
    unittest.main()
