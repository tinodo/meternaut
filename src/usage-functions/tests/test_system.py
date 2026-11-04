import unittest
import uuid
from datetime import timedelta

import support  # noqa: F401  (puts the app folder on the path)

from usage import system


class SystemTests(unittest.TestCase):
    def test_the_clock_gives_an_aware_utc_time(self):
        now = system.utc_now()
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.utcoffset(), timedelta(0))

    def test_the_id_is_a_random_uuid_as_text(self):
        first, second = system.new_uuid(), system.new_uuid()
        self.assertNotEqual(first, second)
        for value in (first, second):
            self.assertIsInstance(value, str)
            self.assertEqual(uuid.UUID(value).version, 4)
            self.assertEqual(value, str(uuid.UUID(value)))


if __name__ == "__main__":
    unittest.main()
