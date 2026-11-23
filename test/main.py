#!/usr/bin/env python3
"""
Test runner cho đồ án LAN Chat & File Sharing.

Gom các module test theo từng nhóm yêu cầu trong bảng điểm và in kết quả
theo từng nhóm, kèm bảng tổng kết ở cuối.

Cách chạy (từ thư mục gốc của project):
    python test/main.py                 # chạy tất cả
    python test/main.py -v              # in từng test case
    python test/main.py -s udp          # chỉ chạy nhóm UDP
    python test/main.py -s tcp file     # chạy nhiều nhóm
    python test/main.py -l              # liệt kê các nhóm

Mã thoát: 0 nếu tất cả test đạt, 1 nếu có test fail/error.
"""

import argparse
import os
import sys
import time
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(TEST_DIR)
for p in (ROOT_DIR, TEST_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_error_handling
import test_file_transfer
import test_protocol
import test_tcp_chat
import test_udp

# key -> (tên nhóm, trọng số trong rubric, module test)
SUITES = {
    "protocol": ("Giao thức & framing TCP", 10, test_protocol),
    "udp": ("UDP discovery, danh sách online, trạng thái", 15, test_udp),
    "tcp": ("TCP chat, unread counter, nhiều peer", 20, test_tcp_chat),
    "file": ("Truyền file, tiến độ, đa luồng", 15, test_file_transfer),
    "error": ("Xử lý lỗi & độ ổn định", 10, test_error_handling),
}


class Result(unittest.TestResult):
    """In kết quả từng test theo dạng một dòng, đồng thời lưu thông tin để tổng kết."""

    def __init__(self, stream, verbose=False):
        super().__init__()
        self.stream = stream
        self.verbose = verbose
        self._t0 = 0.0
        self.timings = {}

    def _write(self, text):
        self.stream.write(text)
        self.stream.flush()

    def startTest(self, test):
        super().startTest(test)
        self._t0 = time.perf_counter()

    def stopTest(self, test):
        self.timings[test.id()] = time.perf_counter() - self._t0
        super().stopTest(test)

    def _report(self, test, label, short):
        if self.verbose:
            name = test.id().split(".", 1)[-1]
            self._write(f"  {label:<5} {name} ({self.timings_so_far():.2f}s)\n")
        else:
            self._write(short)

    def timings_so_far(self):
        return time.perf_counter() - self._t0

    def addSuccess(self, test):
        super().addSuccess(test)
        self._report(test, "ok", ".")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._report(test, "FAIL", "F")

    def addError(self, test, err):
        super().addError(test, err)
        self._report(test, "ERROR", "E")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._report(test, "skip", "s")


def run_suite(key, verbose):
    title, weight, module = SUITES[key]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)

    print(f"\n[{key}] {title} ({weight}%)")
    if not verbose:
        sys.stdout.write("  ")
    result = Result(sys.stdout, verbose)

    start = time.perf_counter()
    suite.run(result)
    elapsed = time.perf_counter() - start
    if not verbose:
        print()

    failed = len(result.failures) + len(result.errors)
    return {
        "key": key,
        "title": title,
        "weight": weight,
        "total": result.testsRun,
        "passed": result.testsRun - failed - len(result.skipped),
        "skipped": len(result.skipped),
        "failed": failed,
        "elapsed": elapsed,
        "problems": [("FAIL", t, e) for t, e in result.failures]
        + [("ERROR", t, e) for t, e in result.errors],
    }


def print_summary(rows, total_time):
    print("\n" + "-" * 72)
    print(f"{'Nhóm':<10}{'Nội dung':<38}{'Điểm':>5}{'Pass':>9}{'Thời gian':>10}")
    print("-" * 72)
    for r in rows:
        title = r["title"] if len(r["title"]) <= 36 else r["title"][:33] + "..."
        ratio = f"{r['passed']}/{r['total']}"
        print(f"{r['key']:<10}{title:<38}{str(r['weight']) + '%':>5}{ratio:>9}{r['elapsed']:>9.2f}s")
    print("-" * 72)

    total = sum(r["total"] for r in rows)
    passed = sum(r["passed"] for r in rows)
    failed = sum(r["failed"] for r in rows)
    skipped = sum(r["skipped"] for r in rows)
    parts = [f"{passed} passed"]
    if failed:
        parts.append(f"{failed} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    print(f"Ran {total} tests in {total_time:.2f}s: " + ", ".join(parts))


def print_problems(rows):
    problems = [p for r in rows for p in r["problems"]]
    if not problems:
        return
    print("\n" + "=" * 72)
    print("CHI TIẾT LỖI")
    print("=" * 72)
    for kind, test, tb in problems:
        print(f"\n{kind}: {test.id()}")
        print("-" * 72)
        print(tb.rstrip())


def main():
    parser = argparse.ArgumentParser(description="Test runner cho đồ án LAN Chat & File Sharing")
    parser.add_argument(
        "-s", "--suite", nargs="+", choices=["all", *SUITES], default=["all"],
        metavar="NHÓM", help="nhóm cần chạy: all, " + ", ".join(SUITES) + " (mặc định: all)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="in từng test case")
    parser.add_argument("-l", "--list", action="store_true", help="liệt kê các nhóm test rồi thoát")
    args = parser.parse_args()

    if args.list:
        for key, (title, weight, _) in SUITES.items():
            print(f"{key:<10}{weight:>3}%  {title}")
        return 0

    keys = list(SUITES) if "all" in args.suite else args.suite

    print(f"LAN Chat & File Sharing - test suite")
    print(f"Python {sys.version.split()[0]} / {sys.platform}")
    print(f"Project: {ROOT_DIR}")

    t0 = time.perf_counter()
    rows = [run_suite(k, args.verbose) for k in keys]
    total_time = time.perf_counter() - t0

    print_problems(rows)
    print_summary(rows, total_time)

    return 1 if any(r["failed"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())