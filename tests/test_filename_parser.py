import unittest

from filename_parser import clean_title, reload_acronyms, search_title_variants


def stem(filename):
    return filename.rsplit(".", 1)[0]


class CleanTitleAmigaTests(unittest.TestCase):
    def test_tosec_multi_disk(self):
        self.assertEqual(
            clean_title(stem("4D Sports Driving (1990)(Mindscape)[cr CSL](Disk 1 of 2).adf")),
            "4D Sports Driving",
        )

    def test_hardware_tag_and_disk_suffix(self):
        self.assertEqual(clean_title(stem("agony(ocs) - d1.adf")), "agony")

    def test_glued_name_with_disk_suffix(self):
        self.assertEqual(clean_title(stem("alteredbeast - d1.adf")), "alteredbeast")

    def test_underscore_disk_number(self):
        self.assertEqual(clean_title(stem("Another world_1.adf")), "Another world")

    def test_glued_lowercase_name(self):
        self.assertEqual(clean_title(stem("afterthewar.adf")), "afterthewar")

    def test_abbreviated_camel_name_with_disk(self):
        self.assertEqual(clean_title(stem("ABreed-d1.adf")), "Alien Breed")

    def test_sequel_with_disk_suffix(self):
        self.assertEqual(clean_title(stem("barbarian2 - d1.adf")), "Barbarian 2")

    def test_scene_abbreviation(self):
        self.assertEqual(clean_title(stem("688attak.adf")), "688attak")

    def test_strips_amiga_platform_prefix(self):
        self.assertEqual(
            clean_title(stem("Amiga Tetris (1987)(Spectrum HoloByte)[cr Defjam - RSi].adf")),
            "Tetris",
        )

    def test_tosec_tank_killer(self):
        self.assertEqual(
            clean_title(stem("A-10 Tank Killer v1.0 (1990)(Sierra)(Disk 1 of 2).adf")),
            "A-10 Tank Killer",
        )

    def test_extra_missions_data_disk(self):
        self.assertEqual(
            clean_title(stem("A-10 Tank Killer - Extra Missions (1990)(Sierra)[data disk].adf")),
            "A-10 Tank Killer - Extra Missions",
        )

    def test_populous_challenge_disk_suffix(self):
        self.assertEqual(clean_title(stem("populous2_challenge.adf")), "Populous 2")

    def test_trailing_article(self):
        self.assertEqual(
            clean_title(stem("Legend of Zelda, The (USA) (Rev 1).nes")),
            "The Legend of Zelda",
        )

    def test_underscore_and_hyphen_disk_suffix(self):
        self.assertEqual(
            clean_title(stem("lords_of_the_rising_sun-1.adf")),
            "lords of the rising sun",
        )

    def test_challenge_disk_suffix(self):
        self.assertEqual(clean_title(stem("populous2_challenge.adf")), "Populous 2")

    def test_hyphenated_title_words(self):
        self.assertEqual(clean_title(stem("marble-madness.adf")), "Marble Madness")


class SearchTitleVariantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reload_acronyms()

    def test_altered_beast_variant(self):
        variants = search_title_variants("alteredbeast")
        self.assertIn("Altered Beast", variants)

    def test_after_the_war_variant(self):
        variants = search_title_variants("afterthewar")
        self.assertIn("After The War", variants)

    def test_alien_breed_variant(self):
        variants = search_title_variants("ABreed")
        self.assertIn("Alien Breed", variants)

    def test_688_attack_variant(self):
        variants = search_title_variants("688attak")
        self.assertIn("688 Attack", variants)

    def test_barbarian_sequel_variant(self):
        variants = search_title_variants("barbarian2")
        self.assertIn("Barbarian 2", variants)
        self.assertIn("Barbarian II", variants)

    def test_double_dragon_variants(self):
        variants = search_title_variants("doubledragon2")
        self.assertIn("Double Dragon 2", variants)
        self.assertIn("Double Dragon II", variants)

    def test_dungeon_master_variant(self):
        variants = search_title_variants("dungeonmaster")
        self.assertIn("Dungeon Master", variants)

    def test_extra_missions_includes_base_game(self):
        title = clean_title(stem("A-10 Tank Killer - Extra Missions (1990)(Sierra)[data disk].adf"))
        variants = search_title_variants(title)
        self.assertIn("A-10 Tank Killer", variants)

    def test_variants_are_case_insensitive_unique(self):
        variants = search_title_variants("Another world")
        lowered = [v.lower() for v in variants]
        self.assertEqual(len(lowered), len(set(lowered)))

    def test_first_variant_is_parsed_title(self):
        variants = search_title_variants("agony")
        self.assertTrue(any(v.lower() == "agony" for v in variants))

    def test_icftd_acronym_expansion(self):
        variants = search_title_variants(clean_title(stem("ICFTD21.adf")))
        self.assertIn("It Came from the Desert", variants)

    def test_lords_of_the_rising_sun(self):
        title = clean_title(stem("lords_of_the_rising_sun-1.adf"))
        variants = search_title_variants(title)
        self.assertIn("Lords Of The Rising Sun", variants)
        self.assertNotIn("Lords Ofthe Rising Sun", variants)

    def test_populous_2_variants(self):
        variants = search_title_variants(clean_title(stem("populous2-d1.adf")))
        self.assertIn("Populous II", variants)

    def test_populous_2_challenge_variants(self):
        variants = search_title_variants(clean_title(stem("populous2_challenge.adf")))
        self.assertIn("Populous II", variants)

    def test_king_of_chicago(self):
        variants = search_title_variants(clean_title(stem("kingofchicago1.adf")))
        self.assertIn("King Of Chicago", variants)

    def test_lotus_3(self):
        variants = search_title_variants(clean_title(stem("lotus3-d1.adf")))
        self.assertIn("Lotus III", variants)

    def test_gauntlet_3(self):
        variants = search_title_variants(clean_title(stem("gauntlet3 - d3.adf")))
        self.assertIn("Gauntlet III", variants)

    def test_maniac_mansion(self):
        variants = search_title_variants(clean_title(stem("maniacmansion - d1.adf")))
        self.assertIn("Maniac Mansion", variants)

    def test_prince_of_persia(self):
        variants = search_title_variants(clean_title(stem("princeofpersia.adf")))
        self.assertIn("Prince Of Persia", variants)

    def test_user_reported_amiga_names(self):
        cases = {
            "Ultima5a.adf": ("Ultima 5", ["Ultima V"]),
            "Ultima5b.adf": ("Ultima 5", ["Ultima V"]),
            "The Lost Vikings Disk1.adf": ("The Lost Vikings", []),
            "TvSportBasketBall-d1.adf": ("Tv Sports Basketball", []),
            "themepa1.adf": ("Theme Park", []),
            "tetrispro.adf": ("Tetris Pro", []),
            "Synd1.adf": ("Syndicate", []),
            "STOOGES1.adf": ("The Three Stooges", []),
            "sinbad1.adf": ("Sinbad and the Throne of the Falcon", []),
            "shadowofthebeast.adf": ("Shadow of the Beast", []),
        }
        for filename, (expected_clean, extra_variants) in cases.items():
            with self.subTest(filename=filename):
                cleaned = clean_title(stem(filename))
                variants = search_title_variants(cleaned)
                self.assertEqual(cleaned.lower(), expected_clean.lower())
                for variant in extra_variants:
                    self.assertIn(variant, variants)

    def test_test_drive_california_challenge_base_game(self):
        title = clean_title(
            stem("Test Drive II - California Challenge (1989)(Accolade)[data disk].adf")
        )
        variants = search_title_variants(title)
        self.assertIn("Test Drive II", variants)

    def test_kick_off_2(self):
        variants = search_title_variants(clean_title(stem("KICKOFF2.ADF")))
        self.assertIn("Kick Off 2", variants)
        self.assertTrue(any("II" in variant for variant in variants))

    def test_user_batch_titles(self):
        cases = {
            "dungeonquest1.adf": "Dungeon Quest",
            "timesoflore.adf": "Times Of Lore",
            "zakmckraken - d1.adf": "Zak Mckracken",
            "f18interceptor.adf": "F-18 Interceptor",
            "Silent Service - The Submarine Simulation v825.01 (1987)(MicroProse).adf": (
                "Silent Service - The Submarine Simulation"
            ),
            "EOTB2-d1.ADF": "Eye of the Beholder 2",
            "F1manag1.adf": "F1 Manager",
            "chasehq.adf": "Chase H.Q.",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(clean_title(stem(filename)), expected)

    def test_silent_service_base_variant(self):
        title = clean_title(
            stem("Silent Service - The Submarine Simulation v825.01 (1987)(MicroProse).adf")
        )
        self.assertIn("Silent Service", search_title_variants(title))

    def test_fighter_bomber_base_variant(self):
        title = clean_title(
            stem("Fighter Bomber - Advanced Mission Disk (1991)(Activision)[data disk].adf")
        )
        self.assertIn("Fighter Bomber", search_title_variants(title))


class CleanTitleFromFilenameTests(unittest.TestCase):
    """End-to-end: full ADF filename -> clean title."""

    CASES = [
        ("agony(ocs) - d1.adf", "agony"),
        ("alteredbeast - d2.adf", "alteredbeast"),
        ("barbarian.adf", "barbarian"),
        ("cannon fodder-d1.adf", "cannon fodder"),
        ("it_came_from_the_desert-1.adf", "it came from the desert"),
        ("lotus3-d2.adf", "Lotus 3"),
        ("ProjectX-d1.adf", "ProjectX"),
    ]

    def test_amiga_adf_filenames(self):
        for filename, expected in self.CASES:
            with self.subTest(filename=filename):
                self.assertEqual(clean_title(stem(filename)), expected)


if __name__ == "__main__":
    unittest.main()
