from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from gain.model.pr import PullRequest

RESPONSIBLE_USE_ADVISORY = (
    "================================================================================\n"
    "[GAIN RESPONSIBLE USE ADVISORY]\n"
    "PR counts reflect workflow inventory, transaction frequency, and batching style.\n"
    "They MUST NOT be used to measure individual developer productivity, effort, or\n"
    "competence, nor for employee evaluation or ranking.\n"
    "(Reference: specs/001-gain-pr-analytics/responsible-use.md)\n"
    "================================================================================"
)


@dataclass(frozen=True)
class MonthlyPRStats:
    month: str  # Format: "YYYY-MM"
    created_count: int
    merged_count: int
    closed_count: int
    closed_unmerged_count: int
    merge_rate_pct: float | None
    repository: str | None = None
    author: str | None = None
    author_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MonthlyStatsMetric:
    metric_id = "GAIN-PR-010"
    metric_version = 1

    @classmethod
    def calculate(
        cls,
        prs: list[PullRequest],
        months: int = 12,
        reference_date: datetime | None = None,
        by_repo: bool = False,
        by_author: bool = False,
        include_bots: bool = True,
    ) -> list[MonthlyPRStats]:
        """Compute monthly created, merged, and closed PR counts for trailing `months`."""
        if not include_bots:
            prs = [p for p in prs if not p.is_bot]

        if reference_date is None:
            reference_date = cls._determine_reference_date(prs)

        target_months = cls._generate_trailing_months(reference_date, months)
        target_months_set = set(target_months)

        # Build group keys: list of (repo_key, author_key)
        groups: list[tuple[str | None, str | None]] = []
        if by_repo and by_author:
            combos: list[tuple[str | None, str | None]] = [
                (r, a)
                for r, a in sorted(
                    {(p.repository_name_with_owner, p.author_login or "unknown") for p in prs}
                )
            ]
            groups = combos if combos else [(None, None)]
        elif by_repo:
            repos = sorted({p.repository_name_with_owner for p in prs})
            groups = [(r, None) for r in (repos if repos else ["all"])]
        elif by_author:
            authors = sorted({p.author_login or "unknown" for p in prs})
            groups = [(None, a) for a in (authors if authors else ["unknown"])]
        else:
            groups = [(None, None)]

        # Map authors to author_type
        author_types: dict[str, str | None] = {}
        for p in prs:
            if p.author_login:
                author_types[p.author_login] = p.author_type

        results: list[MonthlyPRStats] = []

        for repo, author in groups:
            subset = prs
            if repo is not None:
                subset = [p for p in subset if p.repository_name_with_owner == repo]
            if author is not None:
                subset = [p for p in subset if (p.author_login or "unknown") == author]

            created_by_month: dict[str, int] = {m: 0 for m in target_months}
            merged_by_month: dict[str, int] = {m: 0 for m in target_months}
            closed_by_month: dict[str, int] = {m: 0 for m in target_months}
            closed_unmerged_by_month: dict[str, int] = {m: 0 for m in target_months}

            for pr in subset:
                created_key = pr.created_at.strftime("%Y-%m")
                if created_key in target_months_set:
                    created_by_month[created_key] += 1

                if pr.merged_at is not None:
                    merged_key = pr.merged_at.strftime("%Y-%m")
                    if merged_key in target_months_set:
                        merged_by_month[merged_key] += 1

                if pr.closed_at is not None:
                    closed_key = pr.closed_at.strftime("%Y-%m")
                    if closed_key in target_months_set:
                        closed_by_month[closed_key] += 1
                        if pr.merged_at is None:
                            closed_unmerged_by_month[closed_key] += 1

            for m in target_months:
                created = created_by_month[m]
                merged = merged_by_month[m]
                closed = closed_by_month[m]
                closed_unmerged = closed_unmerged_by_month[m]
                merge_rate = round((merged / closed) * 100, 1) if closed > 0 else None

                a_type = author_types.get(author) if author else None

                results.append(
                    MonthlyPRStats(
                        month=m,
                        created_count=created,
                        merged_count=merged,
                        closed_count=closed,
                        closed_unmerged_count=closed_unmerged,
                        merge_rate_pct=merge_rate,
                        repository=repo,
                        author=author,
                        author_type=a_type,
                    )
                )

        return results

    @classmethod
    def _determine_reference_date(cls, prs: list[PullRequest]) -> datetime:
        all_dates: list[datetime] = []
        for pr in prs:
            all_dates.append(pr.created_at)
            if pr.closed_at:
                all_dates.append(pr.closed_at)
            if pr.merged_at:
                all_dates.append(pr.merged_at)
        if all_dates:
            return max(all_dates)
        return datetime.now(UTC)

    @classmethod
    def _generate_trailing_months(cls, ref_date: datetime, count: int) -> list[str]:
        """Generate `count` consecutive YYYY-MM strings ending at `ref_date`'s month."""
        year = ref_date.year
        month = ref_date.month

        months_list: list[str] = []
        for _ in range(count):
            months_list.append(f"{year:04d}-{month:02d}")
            month -= 1
            if month == 0:
                month = 12
                year -= 1

        months_list.reverse()
        return months_list

    @classmethod
    def format_table(cls, stats: list[MonthlyPRStats]) -> str:
        """Format monthly statistics as a clean ASCII table."""
        has_repo = any(s.repository is not None for s in stats)
        has_author = any(s.author is not None for s in stats)

        cols: list[tuple[str, int, str]] = []
        if has_author:
            cols.append(("Author", 16, "<"))
        if has_repo:
            cols.append(("Repository", 22, "<"))

        cols.extend(
            [
                ("Month", 7, "<"),
                ("Created", 7, ">"),
                ("Merged", 7, ">"),
                ("Closed", 7, ">"),
                ("Unmerged", 8, ">"),
                ("Merge Rate", 10, ">"),
            ]
        )

        header = " | ".join(f"{name:{align}{width}}" for name, width, align in cols)
        sep = "-+-".join("-" * width for _, width, _ in cols)

        lines: list[str] = []
        if has_author:
            lines.append(RESPONSIBLE_USE_ADVISORY)
            lines.append("")

        lines.append(header)
        lines.append(sep)

        for s in stats:
            rate_str = f"{s.merge_rate_pct:.1f}%" if s.merge_rate_pct is not None else "N/A"
            row_vals: list[tuple[str, int, str]] = []
            if has_author:
                row_vals.append((s.author or "all", 16, "<"))
            if has_repo:
                row_vals.append((s.repository or "all", 22, "<"))

            row_vals.extend(
                [
                    (s.month, 7, "<"),
                    (str(s.created_count), 7, ">"),
                    (str(s.merged_count), 7, ">"),
                    (str(s.closed_count), 7, ">"),
                    (str(s.closed_unmerged_count), 8, ">"),
                    (rate_str, 10, ">"),
                ]
            )
            lines.append(" | ".join(f"{val:{align}{width}}" for val, width, align in row_vals))

        total_created = sum(s.created_count for s in stats)
        total_merged = sum(s.merged_count for s in stats)
        total_closed = sum(s.closed_count for s in stats)
        total_unmerged = sum(s.closed_unmerged_count for s in stats)
        total_rate_str = (
            f"{(total_merged / total_closed) * 100:.1f}%" if total_closed > 0 else "N/A"
        )

        lines.append(sep)
        total_vals: list[tuple[str, int, str]] = []
        if has_author:
            total_vals.append(("TOTAL", 16, "<"))
        if has_repo:
            if not has_author:
                total_vals.append(("TOTAL", 22, "<"))
            else:
                total_vals.append(("All", 22, "<"))

        total_vals.append(("All" if (has_repo or has_author) else "TOTAL", 7, "<"))
        total_vals.extend(
            [
                (str(total_created), 7, ">"),
                (str(total_merged), 7, ">"),
                (str(total_closed), 7, ">"),
                (str(total_unmerged), 8, ">"),
                (total_rate_str, 10, ">"),
            ]
        )

        lines.append(" | ".join(f"{val:{align}{width}}" for val, width, align in total_vals))
        return "\n".join(lines)
