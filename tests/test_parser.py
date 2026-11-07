import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from clausewitz import ParseError, parse


class ParserTests(unittest.TestCase):
    def test_repeated_keys_are_preserved(self):
        tree = parse('focus = { prerequisite = { focus = a } prerequisite = { focus = b } }')
        self.assertEqual(len(tree.children("focus")[0].children("prerequisite")), 2)

    def test_colour_prefix_and_anonymous_values(self):
        node = parse('color = rgb { 10 20 30 }').children("color")[0]
        self.assertEqual(node.prefix, "rgb")
        self.assertEqual([c.value for c in node.children()], ["10", "20", "30"])

    def test_anonymous_nested_asset_blocks(self):
        node = parse('optional_assets = { { icon = x model = y } }').children()[0]
        self.assertEqual(node.children()[0].scalar("icon"), "x")

    def test_comments_and_quoted_braces(self):
        tree = parse('\ufeff# comment\nname = "a # } \\" b"\nother = "}"')
        self.assertEqual(tree.scalar("name"), 'a # } " b')
        self.assertEqual(tree.scalar("other"), "}")

    def test_quoted_operator_is_a_value(self):
        self.assertEqual(parse('name = "="').scalar("name"), "=")

    def test_comparison_operators(self):
        tree = parse('date > 1991.6.24 num_divisions < 1 chance >= 0.5')
        self.assertEqual([e.op for e in tree.children()], [">", "<", ">="])

    def test_malformed_sources_raise(self):
        for source in ('x = { a = b', 'x = }', '}', 'x = "unclosed', 'x = = y'):
            with self.subTest(source=source), self.assertRaises(ParseError):
                parse(source)


if __name__ == "__main__":
    unittest.main()
