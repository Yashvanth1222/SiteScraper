"""SEO validation for rewritten articles."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SEOResult:
    """Result of an SEO validation check."""

    passed: bool
    score: int  # 0-100
    issues: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"SEO {status} (score: {self.score}/100)"]
        for issue in self.issues:
            lines.append(f"  - {issue}")
        return "\n".join(lines)


class SEOValidator:
    """Validates that a rewritten article meets SEO requirements."""

    # Thresholds
    TITLE_MIN_LEN = 30
    TITLE_MAX_LEN = 70
    META_MIN_LEN = 120
    META_MAX_LEN = 170
    MIN_H2_COUNT = 2
    MIN_WORD_COUNT = 500
    PASS_THRESHOLD = 70  # minimum score to pass

    def validate(
        self,
        title: str,
        meta_description: str,
        body: str,
        keywords: list[str] | None = None,
    ) -> SEOResult:
        """Run all SEO checks and return an ``SEOResult``.

        Parameters
        ----------
        title:
            The article headline.
        meta_description:
            The meta description for search results.
        body:
            The full Markdown body of the article.
        keywords:
            Optional list of target keywords to check for in the body.
        """
        issues: list[str] = []
        total_points = 0
        max_points = 0

        # --- Title length ---
        max_points += 20
        title_len = len(title)
        if self.TITLE_MIN_LEN <= title_len <= self.TITLE_MAX_LEN:
            total_points += 20
        else:
            issues.append(
                f"Title length is {title_len} chars "
                f"(target: {self.TITLE_MIN_LEN}-{self.TITLE_MAX_LEN})"
            )
            # Partial credit if close
            if title_len > 0:
                total_points += 5

        # --- Meta description length ---
        max_points += 20
        meta_len = len(meta_description)
        if self.META_MIN_LEN <= meta_len <= self.META_MAX_LEN:
            total_points += 20
        else:
            issues.append(
                f"Meta description length is {meta_len} chars "
                f"(target: {self.META_MIN_LEN}-{self.META_MAX_LEN})"
            )
            if meta_len > 0:
                total_points += 5

        # --- H2 headings ---
        max_points += 20
        h2_count = len(re.findall(r"^## ", body, re.MULTILINE))
        if h2_count >= self.MIN_H2_COUNT:
            total_points += 20
        else:
            issues.append(
                f"Found {h2_count} H2 headings (minimum: {self.MIN_H2_COUNT})"
            )
            total_points += min(h2_count * 10, 15)

        # --- Word count ---
        max_points += 20
        word_count = len(body.split())
        if word_count >= self.MIN_WORD_COUNT:
            total_points += 20
        else:
            issues.append(
                f"Word count is {word_count} (minimum: {self.MIN_WORD_COUNT})"
            )
            total_points += min(int(word_count / self.MIN_WORD_COUNT * 15), 15)

        # --- Keywords ---
        max_points += 10
        if keywords:
            body_lower = body.lower()
            found = sum(1 for kw in keywords if kw.lower() in body_lower)
            if found == len(keywords):
                total_points += 10
            elif found > 0:
                total_points += int(found / len(keywords) * 10)
                missing = [kw for kw in keywords if kw.lower() not in body_lower]
                issues.append(f"Missing keywords: {', '.join(missing)}")
            else:
                issues.append(f"No target keywords found in body")
        else:
            # No keywords specified — give full credit
            total_points += 10

        # --- Internal link placeholder ---
        max_points += 10
        if "{{novig_internal_link}}" in body:
            total_points += 10
        else:
            issues.append("Missing {{novig_internal_link}} placeholder")

        score = int(total_points / max_points * 100) if max_points > 0 else 0
        passed = score >= self.PASS_THRESHOLD

        return SEOResult(passed=passed, score=score, issues=issues)
