# -*- coding: utf-8 -*-
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "stop-slop-ko" / "skills" / "stop-slop-ko" / "scripts" / "slop_scan.py"
sys.path.insert(0, str(SCRIPT.parent))

import slop_scan as S  # noqa: E402

FILLER = "회사는 작년부터 재택근무를 시범 운영했고 올해 전 부서로 넓혔다."  # 35자


def body(n_chars):
    """n_chars 안팎의 평범한 문단들."""
    paras, total = [], 0
    while total < n_chars:
        paras.append(FILLER)
        total += len(FILLER)
    return paras


class Base(unittest.TestCase):
    def md(self, lines):
        d = tempfile.mkdtemp()
        p = Path(d) / "t.md"
        p.write_text("\n\n".join(lines), encoding="utf-8")
        return p

    def codes(self, lines, prose=True, info=True):
        return [h[1] for h in S.scan(self.md(lines), info, prose)]


class NoProseUnchanged(Base):
    def test_prose_rules_off_by_default(self):
        lines = ["본 보고서에서는 재택근무를 알아보고자 한다.", "협업의 중요성을 깨달았다."]
        self.assertFalse([c for c in self.codes(lines, prose=False) if c.startswith("PROSE")])

    def test_existing_rules_still_fire_with_prose(self):
        self.assertIn("EMDASH", self.codes(["재택근무 — 장점이 많다."]))


class LineInfo(Base):
    def test_lesson(self):
        self.assertIn("PROSE_LESSON", self.codes(["이 일로 협업의 중요성을 깨달았다."]))

    def test_notjust(self):
        self.assertIn("PROSE_NOTJUST", self.codes(["단순한 과제가 아닌 도전이었다."]))

    def test_empty_emph(self):
        self.assertIn("PROSE_EMPTY_EMPH", self.codes(["정말 많은 것을 배웠다."]))

    def test_report_cliche(self):
        self.assertIn("PROSE_CLICHE_REPORT", self.codes(["본 보고서에서는 재택근무를 알아보고자 한다."]))

    def test_blog_cliche(self):
        self.assertIn("PROSE_CLICHE_BLOG", self.codes(["오늘은 Docker 볼륨에 대해 알아보겠습니다."]))

    def test_quote_open_first_paragraph_only(self):
        self.assertIn("PROSE_QUOTE_OPEN", self.codes(["# 제목", "“실패는 성공의 어머니”라는 말이 있다.", FILLER]))
        self.assertNotIn("PROSE_QUOTE_OPEN", self.codes([FILLER, "“실패는 성공의 어머니”라는 말이 있다."]))

    def test_info_hidden_without_flag(self):
        self.assertFalse(self.codes(["협업의 중요성을 깨달았다."], info=False))


class Minor121(Base):
    def test_notjust_variants(self):
        for line in ["단순 작업이 아니라 설계였다.", "그저 숫자가 아닌 사람 이야기다.",
                     "단지 비용 절감이 아니라 방향 전환이다.", "재택근무는 비용 절감에 그치지 않고 채용까지 바꿨다."]:
            self.assertIn("PROSE_NOTJUST", self.codes([line]), line)

    def test_notjust_plain_not_hit(self):
        self.assertNotIn("PROSE_NOTJUST", self.codes(["작업이 단순해서 금방 끝났다."]))

    def test_think_variants_counted(self):
        variants = ["이 방식이 맞다고 생각된다.", "이 방식이 맞다는 생각이 든다.", "이 방식이 맞다고 본다.",
                    "이 방식이 맞다고 봅니다."]
        for v in variants:
            self.assertIn("PROSE_THINK", self.codes(body(700) + [v] * 3), v)

    def test_conditional_not_counted(self):
        lines = ["A가 맞다고 본다면 대조군으로 검증한다.", "B가 맞다고 생각한다면 표본을 늘린다.",
                 "C가 맞다는 생각이 든다면 반례부터 찾는다."]
        self.assertNotIn("PROSE_THINK", self.codes(body(700) + lines))

    def test_plain_bonda_not_counted(self):
        self.assertNotIn("PROSE_THINK", self.codes(body(700) + ["결과를 다시 본다."] * 3))


class ThinkWarn(Base):
    T = "나는 이 방식이 맞다고 생각한다."

    def test_short_two_pass(self):
        self.assertNotIn("PROSE_THINK", self.codes(body(700) + [self.T] * 2))

    def test_short_three_warn(self):
        hits = S.scan(self.md(body(700) + [self.T] * 3), False, True)
        warn = [h for h in hits if h[1] == "PROSE_THINK"]
        self.assertEqual(warn[0][0], "WARN")
        self.assertIn("3회", warn[0][3])

    def test_long_three_pass(self):
        self.assertNotIn("PROSE_THINK", self.codes(body(6000) + [self.T] * 3))

    def test_long_dense_warn(self):
        self.assertIn("PROSE_THINK", self.codes(body(6000) + [self.T] * 7))


class ConnectorWarn(Base):
    C = "또한 재택근무는 통근 시간을 줄였다."

    def test_three_of_six_warn(self):
        self.assertIn("PROSE_CONNECTOR", self.codes([FILLER] * 3 + [self.C] * 3))

    def test_three_of_twenty_pass(self):
        self.assertNotIn("PROSE_CONNECTOR", self.codes([FILLER] * 17 + [self.C] * 3))

    def test_two_pass(self):
        self.assertNotIn("PROSE_CONNECTOR", self.codes([FILLER] * 2 + [self.C] * 2))

    def test_headings_not_counted(self):
        # 문단 9개 중 3개(33%) → WARN. 제목 줄 4개가 분모에 들어가면 23%로 PASS가 되어 버린다
        lines = ["# 1장", "# 2장", "# 3장", "# 4장"] + [FILLER] * 6 + [self.C] * 3
        self.assertIn("PROSE_CONNECTOR", self.codes(lines))


class ParagraphGrouping(Base):
    def test_md_wrapped_lines_are_one_paragraph(self):
        p = Path(tempfile.mkdtemp()) / "t.md"
        p.write_text(FILLER + "\n또한 한 줄.\n따라서 두 줄.\n그러므로 세 줄.\n", encoding="utf-8")
        self.assertNotIn("PROSE_CONNECTOR", [h[1] for h in S.scan(p, True, True)])

    def test_blank_line_paragraphs_in_one_cell(self):
        paras = [("A1", "\n\n".join([FILLER, "또한 하나.", "또한 둘.", "또한 셋."]))]
        self.assertIn("PROSE_CONNECTOR", [h[1] for h in S.prose_totals(S.split_paragraphs(paras), True)])


class ReviewFixes(Base):
    C3 = ["또한 하나.", "나아가 둘.", "따라서 셋."]

    def write(self, name, text):
        p = Path(tempfile.mkdtemp()) / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_md_table_cells_not_counted(self):
        table = "\n".join(["| 항목 | 설명 |", "|---|---|"] + [f"| 항목{i} | 설명입니다 |" for i in range(4)])
        p = self.write("t.md", "\n\n".join([FILLER] + self.C3) + "\n\n" + table + "\n")
        self.assertIn("PROSE_CONNECTOR", [h[1] for h in S.scan(p, True, True)])

    def test_txt_single_newline_paragraphs(self):
        p = self.write("t.txt", "\n".join([FILLER] + self.C3) + "\n")
        self.assertIn("PROSE_CONNECTOR", [h[1] for h in S.scan(p, True, True)])

    def test_front_matter_skipped(self):
        p = self.write("t.md", "---\ntitle: 새 도구 후기\n---\n\n“실패는 성공의 어머니”라는 말이 있다.\n")
        self.assertIn("PROSE_QUOTE_OPEN", [h[1] for h in S.scan(p, True, True)])

    def test_blockquote_open(self):
        self.assertIn("PROSE_QUOTE_OPEN", self.codes(["> “실패는 성공의 어머니”", FILLER]))

    def test_front_matter_still_scanned_without_prose(self):
        p = self.write("t.md", "---\ntitle: 재택근무 — 후기\n---\n")
        self.assertIn("EMDASH", [h[1] for h in S.scan(p, False, False)])


class Cli(Base):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True)

    def test_exit_codes(self):
        p = self.md(body(700) + ["맞다고 생각한다."] * 3)
        self.assertEqual(self.run_cli(str(p)).returncode, 0)
        self.assertEqual(self.run_cli(str(p), "--prose").returncode, 1)


class ForkRules(Base):
    def codes(self, lines):
        return [h[1] for h in S.scan(self.md(lines), True, False)]

    def test_rieum_noun_warns(self):
        self.assertIn("NOUN_RIEUM", self.codes(["새 화면을 만듦", "팀을 이끎"]))

    def test_rieum_word_kept(self):
        self.assertNotIn("NOUN_RIEUM", self.codes(["제품의 만듦새가 좋다."]))

    def test_poetic_title_info(self):
        self.assertIn("POETIC_TITLE", self.codes(["# 팬 반응과 곡의 결"]))

    def test_long_sentence_not_poetic(self):
        self.assertNotIn("POETIC_TITLE", self.codes(["이번 분기 서버실 냉각 장치를 교체해서 측정한 서버실 내부의 온도"]))


if __name__ == "__main__":
    unittest.main()


class ChatEndings(Base):
    def chat(self, lines, info=True):
        return [h[1] for h in S.scan(self.md(lines), info, False, True)]

    def test_yo_run_warns(self):
        lines = ["머지 뒤에 코드 보다가 두 가지가 보였어요.",
                 "그 문서 행이 빠진 채 상태가 저장돼요. 다음 회차에 행 수백 개가 나가요.",
                 "`MORE_MAX` 링크가 바뀌어도 마찬가지예요."]
        self.assertIn("CHAT_ENDING_RUN", self.chat(lines))

    def test_hamnida_run_warns(self):
        lines = ["확인했습니다.", "규칙이 좋습니다.", "머지하겠습니다.", "다음에 보겠습니다."]
        self.assertIn("CHAT_ENDING_RUN", self.chat(lines))

    def test_mixed_passes(self):
        lines = ["머지 뒤에 코드 보다가 두 가지가 보였습니다.",
                 "그 문서 행이 빠진 채 상태가 저장돼요. 다음 회차에 행 수백 개가 나갑니다.",
                 "링크가 바뀌어도 마찬가지예요. 기준선을 다시 잡으면 좋겠습니다."]
        self.assertFalse([c for c in self.chat(lines) if c.startswith("CHAT")])

    def test_off_by_default(self):
        lines = ["보였어요.", "저장돼요.", "나가요.", "좋겠어요."]
        self.assertFalse([c for c in self.codes(lines, prose=False) if c.startswith("CHAT")])

    def test_gaejo_and_plain_not_counted(self):
        lines = ["- 문서 행이 빠짐", "- 다음 회차에 다시 나감", "회차마다 시작 위치를 돌린다.", "상한을 넘는다."]
        self.assertFalse([c for c in self.chat(lines) if c.startswith("CHAT")])

    def test_one_register_info(self):
        mixed = self.chat(["보였어요.", "저장돼요.", "나갑니다.", "좋겠어요.", "넘어요.", "빠져요."])
        self.assertNotIn("CHAT_ONE_REGISTER", mixed)
        same = self.chat(["보였어요.", "저장돼요.", "나갑니다.", "좋겠어요.", "넘어요.", "빠져요.", "됩니다."])
        self.assertNotIn("CHAT_ONE_REGISTER", same)
        one = self.chat(["보였어요.", "저장돼요.", "나가요.", "좋겠어요.", "넘어요."])
        self.assertIn("CHAT_ONE_REGISTER", one)

    def test_ending_family(self):
        self.assertEqual(S.ending_family("돌려 주세요."), "해요")
        self.assertEqual(S.ending_family("좋겠습니다!"), "습니다")
        self.assertEqual(S.ending_family("48시간까지만요"), "해요")
        self.assertIsNone(S.ending_family("상한을 넘는다."))
        self.assertIsNone(S.ending_family("문서 행이 빠짐"))
