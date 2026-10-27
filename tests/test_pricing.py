"""Current fare rules without the retired anonymous-ride HTTP assumptions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class PricingTests(unittest.TestCase):
    def test_dispatch_rates_apply_to_both_distance_legs(self):
        rates = {"flag_drop": 4.5, "trip_per_mile": 2.0,
                 "approach_per_mile": 0.5, "multiplier": 1.25}
        breakdown = server.fare_breakdown(6, 2, rates)
        self.assertEqual(breakdown["total"], 21.88)
        self.assertEqual(server.fare(6, 2, rates), breakdown["total"])
        self.assertEqual(breakdown["trip_mi"], 6)
        self.assertEqual(breakdown["driver_to_pickup_mi"], 2)

    def test_invalid_dispatch_rates_cannot_be_saved(self):
        rates = {"flag_drop": 5, "trip_per_mile": 1,
                 "approach_per_mile": 0.25, "multiplier": 1}
        self.assertIsNone(server.validate_pricing(dict(rates, multiplier=0))[0])
        self.assertIsNone(server.validate_pricing(dict(rates, trip_per_mile=float("nan")))[0])
        self.assertIsNone(server.validate_pricing(dict(rates, flag_drop=-1))[0])
        self.assertEqual(server.validate_pricing(rates)[0], rates)


if __name__ == "__main__":
    unittest.main()
