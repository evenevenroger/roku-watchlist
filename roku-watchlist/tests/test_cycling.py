import unittest

from watchlist import cycling

CALENDAR = """<table><tbody>
<tr class=""><td class="cu500" >19.01 - 24.01</td><td class="hide cs500" >19.01</td><td><span class="flag au"></span> <a  href="race/tour-down-under-2027-gc">Santos Tour Down Under</a></td><td class="cu500" ><a  href="rider/"></a></td><td>2.UWT</td></tr>
<tr class=""><td class="cu500" >11.04</td><td class="hide cs500" >11.04</td><td><span class="flag fr"></span> <a  href="race/paris-roubaix-2027-result">Paris-Roubaix Hauts-de-France</a></td><td class="cu500" ><a  href="rider/"></a></td><td>1.UWT</td></tr>
</tbody></table>"""

STAGES = """<table><tbody>
<tr class=""><td>07/04</td><td><span class="icon profile p3 mg_rp4 "></span></td><td class="mb_w90" ><a  href="race/tour-de-france-2026-stage-1">Stage 1 (TTT) | Barcelona - Barcelona</a></td></tr>
<tr class=""><td>07/05</td><td><span class="icon profile p0 mg_rp4 "></span></td><td class="mb_w90" ><a  href="race/tour-de-france-2026-stage-2">Stage 2 | - </a></td></tr>
</tbody></table>"""

INFO = """<div class="bold mr5" style="display: inline-block;">Start time: </div><div class="" style="display: inline-block;">11:05:00</div><br />
<div class="bold mr5" style="display: inline-block;">Distance:</div><div class="mr3" style="display: inline-block;">258.3</div><div class="" style="display: inline-block;">km</div><br />
<div class="bold mr5" style="display: inline-block;">Parcours type: </div><div class="" style="display: inline-block;"><span class="icon profile p1 mg_rp4 "></span></div><div>Flat</div><br />
<div class="bold mr5" style="display: inline-block;">Departure:</div><div class="" style="display: inline-block;"><a href="x">Compiègne</a></div><br />
<div class="bold mr5" style="display: inline-block;">Arrival:</div><div class="" style="display: inline-block;"><a href="y">Roubaix</a></div><br />"""


class CyclingParserTests(unittest.TestCase):
    def test_calendar(self):
        races = cycling.parse_calendar(CALENDAR, 2027)
        self.assertEqual([r["slug"] for r in races], ["tour-down-under", "paris-roubaix"])
        self.assertEqual((races[0]["start"], races[0]["end"], races[0]["cc"]), ("2027-01-19", "2027-01-24", "au"))
        self.assertEqual(races[1]["start"], races[1]["end"])

    def test_stages_ignore_placeholders(self):
        stages = cycling.parse_stages(STAGES, 2026)
        self.assertEqual(stages[0]["profile"], "p3")
        self.assertEqual((stages[0]["from"], stages[0]["to"]), ("Barcelona", "Barcelona"))
        self.assertEqual((stages[1]["profile"], stages[1]["from"], stages[1]["to"]), ("", "", ""))

    def test_info(self):
        info = cycling.parse_info(INFO)
        self.assertEqual(info, {"time": "11:05", "km": 258.3, "from": "Compiègne", "to": "Roubaix", "profile": "p1"})
        self.assertNotIn("time", cycling.parse_info(INFO.replace("11:05:00", "00:00:00")))

    def test_start_time_in_brasilia(self):
        europe = {"slug": "paris-roubaix", "cc": "fr"}
        self.assertEqual(cycling._to_brt(europe, "2027-04-11", "11:05"), ("2027-04-11", "06:05"))
        adelaide = {"slug": "tour-down-under", "cc": "au"}
        self.assertEqual(cycling._to_brt(adelaide, "2027-01-19", "11:00"), ("2027-01-18", "21:30"))

    def test_watch_texts(self):
        t = cycling._watch_texts({"br": [{"service": "ESPN / Disney+"}],
                                  "abroad": [{"service": "SBS On Demand", "country": "au", "lang": "en", "free": True}]})
        self.assertEqual(t["apps"], [{"label": "Disney+", "id": "291097"}])
        self.assertEqual(t["vpnShort"], "VPN: SBS On Demand (AU, grátis)")
        self.assertIn("Austrália", t["vpnLines"][0])


if __name__ == "__main__":
    unittest.main()
