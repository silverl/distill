"""Pattern detection analyzers for session insights.

This module provides analyzers that detect patterns in session data:
- SuccessFailureAnalyzer: Identifies patterns in successful vs failed approaches
- TimelineAnalyzer: Detects temporal patterns (daily/weekly cycles)
- CrossSessionCorrelator: Finds relationships between sessions across sources
"""

import hashlib
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import UTC, datetime

from distill.models import BaseSession
from distill.models.insight import (
    Insight,
    InsightCollection,
    InsightSeverity,
    InsightType,
)


class BaseAnalyzer(ABC):
    """Base class for session analyzers."""

    @abstractmethod
    def analyze(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze sessions and return insights.

        Args:
            sessions: List of sessions to analyze.

        Returns:
            List of insights derived from the sessions.
        """
        pass

    def _generate_insight_id(self, *parts: str) -> str:
        """Generate a deterministic insight ID from parts."""
        combined = "-".join(str(p) for p in parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:12]


class SuccessFailureAnalyzer(BaseAnalyzer):
    """Analyzes patterns in successful vs failed approaches.

    This analyzer examines session outcomes to identify:
    - Tools that correlate with success
    - Common patterns in failed sessions
    - Recovery strategies that work
    """

    def analyze(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze sessions for success/failure patterns.

        Args:
            sessions: List of sessions to analyze.

        Returns:
            List of insights about success/failure patterns.
        """
        insights: list[Insight] = []

        if len(sessions) < 2:
            return insights

        # Categorize sessions by outcome
        successful_sessions = [s for s in sessions if self._is_successful(s)]
        failed_sessions = [s for s in sessions if not self._is_successful(s)]

        # Analyze tool usage in successful vs failed sessions
        insights.extend(self._analyze_tool_patterns(successful_sessions, failed_sessions))

        # Analyze session duration patterns
        insights.extend(self._analyze_duration_patterns(successful_sessions, failed_sessions))

        # Analyze tag patterns
        insights.extend(self._analyze_tag_patterns(successful_sessions, failed_sessions))

        return insights

    def _is_successful(self, session: BaseSession) -> bool:
        """Determine if a session was successful.

        Uses outcomes if available, otherwise infers from metadata.
        """
        if session.outcomes:
            # If there are outcomes, check if any succeeded
            return any(o.success for o in session.outcomes)

        # Infer from metadata or default to True (no explicit failure)
        return session.metadata.get("success", True)

    def _analyze_tool_patterns(
        self,
        successful: list[BaseSession],
        failed: list[BaseSession],
    ) -> list[Insight]:
        """Identify tools that correlate with success or failure."""
        insights: list[Insight] = []

        # Count tools in each category
        success_tools: Counter[str] = Counter()
        failure_tools: Counter[str] = Counter()

        for session in successful:
            for tool in session.tools_used:
                success_tools[tool.name] += tool.count

        for session in failed:
            for tool in session.tools_used:
                failure_tools[tool.name] += tool.count

        # Find tools that appear significantly more in successful sessions
        all_tools = set(success_tools.keys()) | set(failure_tools.keys())
        total_success = sum(success_tools.values()) or 1
        total_failure = sum(failure_tools.values()) or 1

        for tool in all_tools:
            success_rate = success_tools.get(tool, 0) / total_success
            failure_rate = failure_tools.get(tool, 0) / total_failure

            if success_rate > failure_rate * 1.5 and success_tools.get(tool, 0) >= 3:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("success_tool", tool),
                        type=InsightType.SUCCESS_PATTERN,
                        title=f"Tool '{tool}' correlates with success",
                        description=(
                            f"Sessions using '{tool}' tend to be more successful. "
                            f"This tool appears {success_tools[tool]} times in successful sessions."
                        ),
                        severity=InsightSeverity.MEDIUM,
                        confidence=min(0.9, 0.5 + (success_rate - failure_rate)),
                        evidence={
                            "tool": tool,
                            "success_count": success_tools[tool],
                            "failure_count": failure_tools.get(tool, 0),
                            "success_rate": success_rate,
                        },
                        recommendations=[
                            f"Consider using '{tool}' more frequently in similar tasks",
                        ],
                    )
                )
            elif failure_rate > success_rate * 1.5 and failure_tools.get(tool, 0) >= 3:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("failure_tool", tool),
                        type=InsightType.FAILURE_PATTERN,
                        title=f"Tool '{tool}' appears often in failed sessions",
                        description=(
                            f"Sessions using '{tool}' have a higher failure rate. "
                            f"This tool appears {failure_tools[tool]} times in failed sessions."
                        ),
                        severity=InsightSeverity.HIGH,
                        confidence=min(0.9, 0.5 + (failure_rate - success_rate)),
                        evidence={
                            "tool": tool,
                            "success_count": success_tools.get(tool, 0),
                            "failure_count": failure_tools[tool],
                            "failure_rate": failure_rate,
                        },
                        recommendations=[
                            f"Review how '{tool}' is being used in problematic cases",
                            "Consider alternative approaches when this pattern emerges",
                        ],
                    )
                )

        return insights

    def _analyze_duration_patterns(
        self,
        successful: list[BaseSession],
        failed: list[BaseSession],
    ) -> list[Insight]:
        """Analyze session duration patterns for success/failure."""
        insights: list[Insight] = []

        success_durations = [s.duration_minutes for s in successful if s.duration_minutes]
        failure_durations = [s.duration_minutes for s in failed if s.duration_minutes]

        if len(success_durations) >= 3 and len(failure_durations) >= 3:
            avg_success = sum(success_durations) / len(success_durations)
            avg_failure = sum(failure_durations) / len(failure_durations)

            if avg_failure > avg_success * 1.5:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("duration_failure"),
                        type=InsightType.FAILURE_PATTERN,
                        title="Failed sessions tend to be longer",
                        description=(
                            f"Failed sessions average {avg_failure:.1f} minutes vs "
                            f"{avg_success:.1f} minutes for successful ones. "
                            "Consider breaking down complex tasks or seeking help earlier."
                        ),
                        severity=InsightSeverity.MEDIUM,
                        confidence=0.7,
                        evidence={
                            "avg_success_duration": avg_success,
                            "avg_failure_duration": avg_failure,
                            "sample_size_success": len(success_durations),
                            "sample_size_failure": len(failure_durations),
                        },
                        recommendations=[
                            "Set time limits for difficult tasks",
                            "Break large tasks into smaller sessions",
                        ],
                    )
                )

        return insights

    def _analyze_tag_patterns(
        self,
        successful: list[BaseSession],
        failed: list[BaseSession],
    ) -> list[Insight]:
        """Analyze tag patterns in success/failure."""
        insights: list[Insight] = []

        success_tags: Counter[str] = Counter()
        failure_tags: Counter[str] = Counter()

        for session in successful:
            success_tags.update(session.tags)

        for session in failed:
            failure_tags.update(session.tags)

        # Find tags with significant differences
        for tag, count in failure_tags.most_common(5):
            if count >= 3 and count > success_tags.get(tag, 0) * 2:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("failure_tag", tag),
                        type=InsightType.FAILURE_PATTERN,
                        title=f"Tag '{tag}' associated with failures",
                        description=(
                            f"Sessions tagged '{tag}' have a high failure rate. "
                            f"Found {count} failed sessions vs "
                            f"{success_tags.get(tag, 0)} successful."
                        ),
                        severity=InsightSeverity.MEDIUM,
                        confidence=0.6,
                        evidence={
                            "tag": tag,
                            "failure_count": count,
                            "success_count": success_tags.get(tag, 0),
                        },
                        recommendations=[
                            f"Review approach when working on '{tag}' tasks",
                        ],
                    )
                )

        return insights


class TimelineAnalyzer(BaseAnalyzer):
    """Analyzes temporal patterns in sessions.

    This analyzer detects:
    - Daily productivity patterns (peak hours)
    - Weekly productivity patterns (best days)
    - Session frequency trends
    - Time-based success patterns
    """

    def analyze(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze sessions for temporal patterns.

        Args:
            sessions: List of sessions to analyze.

        Returns:
            List of insights about temporal patterns.
        """
        insights: list[Insight] = []

        if len(sessions) < 5:
            return insights

        # Analyze hourly patterns
        insights.extend(self._analyze_hourly_patterns(sessions))

        # Analyze daily patterns (day of week)
        insights.extend(self._analyze_daily_patterns(sessions))

        # Analyze session frequency trends
        insights.extend(self._analyze_frequency_trends(sessions))

        # Analyze duration by time of day
        insights.extend(self._analyze_duration_by_time(sessions))

        return insights

    def _analyze_hourly_patterns(self, sessions: list[BaseSession]) -> list[Insight]:
        """Identify peak productivity hours."""
        insights: list[Insight] = []

        hour_counts: Counter[int] = Counter(s.start_time.hour for s in sessions)

        if not hour_counts:
            return insights

        # Find peak hours
        peak_hours = hour_counts.most_common(3)
        peak_hour = peak_hours[0][0]
        peak_count = peak_hours[0][1]

        # Find low-activity hours
        all_hours = set(range(24))
        active_hours = set(hour_counts.keys())
        all_hours - active_hours

        # Morning (6-12), afternoon (12-18), evening (18-24), night (0-6)
        time_periods = {
            "morning": range(6, 12),
            "afternoon": range(12, 18),
            "evening": range(18, 24),
            "night": list(range(0, 6)),
        }

        period_counts: dict[str, int] = {}
        for period, hours in time_periods.items():
            period_counts[period] = sum(hour_counts.get(h, 0) for h in hours)

        peak_period = max(period_counts, key=lambda k: period_counts[k])

        # Generate insight about peak activity time
        session_ids = [s.id for s in sessions if s.start_time.hour == peak_hour][:5]
        insights.append(
            Insight(
                id=self._generate_insight_id("peak_hour", str(peak_hour)),
                type=InsightType.TIMELINE_PATTERN,
                title=f"Peak productivity at {peak_hour}:00",
                description=(
                    f"Most sessions ({peak_count}) start around {peak_hour}:00. "
                    f"Your most active period is the {peak_period}."
                ),
                severity=InsightSeverity.LOW,
                confidence=0.8,
                session_ids=session_ids,
                evidence={
                    "peak_hour": peak_hour,
                    "peak_count": peak_count,
                    "peak_period": peak_period,
                    "hourly_distribution": dict(hour_counts),
                    "period_distribution": period_counts,
                },
                recommendations=[
                    f"Schedule important tasks around {peak_hour}:00",
                    f"Consider batching similar work during {peak_period} hours",
                ],
            )
        )

        return insights

    def _analyze_daily_patterns(self, sessions: list[BaseSession]) -> list[Insight]:
        """Identify weekly patterns."""
        insights: list[Insight] = []

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts: Counter[int] = Counter(s.start_time.weekday() for s in sessions)

        if len(day_counts) < 3:
            return insights

        peak_day = day_counts.most_common(1)[0]
        low_day = day_counts.most_common()[-1]

        # Calculate weekday vs weekend ratio
        weekday_count = sum(day_counts.get(d, 0) for d in range(5))
        weekend_count = sum(day_counts.get(d, 0) for d in range(5, 7))

        session_ids = [s.id for s in sessions if s.start_time.weekday() == peak_day[0]][:5]
        insights.append(
            Insight(
                id=self._generate_insight_id("peak_day", str(peak_day[0])),
                type=InsightType.TIMELINE_PATTERN,
                title=f"Most productive on {day_names[peak_day[0]]}s",
                description=(
                    f"{day_names[peak_day[0]]} has the most sessions ({peak_day[1]}). "
                    f"Least active day is {day_names[low_day[0]]} ({low_day[1]} sessions)."
                ),
                severity=InsightSeverity.LOW,
                confidence=0.75,
                session_ids=session_ids,
                evidence={
                    "peak_day": day_names[peak_day[0]],
                    "peak_count": peak_day[1],
                    "low_day": day_names[low_day[0]],
                    "low_count": low_day[1],
                    "weekday_count": weekday_count,
                    "weekend_count": weekend_count,
                    "daily_distribution": {day_names[d]: c for d, c in day_counts.items()},
                },
                recommendations=[
                    f"Plan critical work for {day_names[peak_day[0]]}s when possible",
                ],
            )
        )

        return insights

    def _analyze_frequency_trends(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze session frequency over time."""
        insights: list[Insight] = []

        if len(sessions) < 10:
            return insights

        # Sort sessions by time
        sorted_sessions = sorted(sessions, key=lambda s: s.start_time)

        # Calculate daily session counts for the last 30 days
        now = datetime.now(UTC)
        last_30_days = [s for s in sorted_sessions if (now - s.start_time).days <= 30]
        previous_30_days = [s for s in sorted_sessions if 30 < (now - s.start_time).days <= 60]

        if len(last_30_days) >= 5 and len(previous_30_days) >= 5:
            recent_avg = len(last_30_days) / 30
            previous_avg = len(previous_30_days) / 30

            if recent_avg > previous_avg * 1.3:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("frequency_increase"),
                        type=InsightType.PRODUCTIVITY_INSIGHT,
                        title="Session frequency is increasing",
                        description=(
                            f"You've had {len(last_30_days)} sessions in the last 30 days, "
                            f"up from {len(previous_30_days)} in the previous period. "
                            "Productivity is trending upward!"
                        ),
                        severity=InsightSeverity.LOW,
                        confidence=0.7,
                        evidence={
                            "recent_count": len(last_30_days),
                            "previous_count": len(previous_30_days),
                            "recent_avg_per_day": recent_avg,
                            "previous_avg_per_day": previous_avg,
                        },
                    )
                )
            elif recent_avg < previous_avg * 0.7:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("frequency_decrease"),
                        type=InsightType.PRODUCTIVITY_INSIGHT,
                        title="Session frequency is decreasing",
                        description=(
                            f"You've had {len(last_30_days)} sessions in the last 30 days, "
                            f"down from {len(previous_30_days)} in the previous period."
                        ),
                        severity=InsightSeverity.MEDIUM,
                        confidence=0.7,
                        evidence={
                            "recent_count": len(last_30_days),
                            "previous_count": len(previous_30_days),
                            "recent_avg_per_day": recent_avg,
                            "previous_avg_per_day": previous_avg,
                        },
                    )
                )

        return insights

    def _analyze_duration_by_time(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze how session duration varies by time of day."""
        insights: list[Insight] = []

        # Group sessions by time period
        morning_durations: list[float] = []
        afternoon_durations: list[float] = []
        evening_durations: list[float] = []

        for session in sessions:
            if session.duration_minutes is None:
                continue
            hour = session.start_time.hour
            if 6 <= hour < 12:
                morning_durations.append(session.duration_minutes)
            elif 12 <= hour < 18:
                afternoon_durations.append(session.duration_minutes)
            elif 18 <= hour < 24:
                evening_durations.append(session.duration_minutes)

        # Find the period with longest average session
        periods = {
            "morning": morning_durations,
            "afternoon": afternoon_durations,
            "evening": evening_durations,
        }

        avg_durations: dict[str, float] = {}
        for period, durations in periods.items():
            if len(durations) >= 3:
                avg_durations[period] = sum(durations) / len(durations)

        if len(avg_durations) >= 2:
            max_period = max(avg_durations, key=lambda k: avg_durations[k])
            min_period = min(avg_durations, key=lambda k: avg_durations[k])

            if avg_durations[max_period] > avg_durations[min_period] * 1.5:
                insights.append(
                    Insight(
                        id=self._generate_insight_id("duration_by_time"),
                        type=InsightType.TIMELINE_PATTERN,
                        title=f"Longer sessions in the {max_period}",
                        description=(
                            f"Sessions in the {max_period} average "
                            f"{avg_durations[max_period]:.1f} minutes, compared to "
                            f"{avg_durations[min_period]:.1f} minutes in the {min_period}."
                        ),
                        severity=InsightSeverity.LOW,
                        confidence=0.65,
                        evidence={
                            "period_averages": avg_durations,
                            "sample_sizes": {p: len(d) for p, d in periods.items()},
                        },
                        recommendations=[
                            f"Consider scheduling complex tasks for the {max_period}",
                        ],
                    )
                )

        return insights


class CrossSessionCorrelator(BaseAnalyzer):
    """Finds relationships between sessions across different sources.

    This analyzer identifies:
    - Sessions that relate to the same project/topic
    - Patterns across .claude, .codex, and .vermas sources
    - Session chains (related sequential work)
    """

    def analyze(self, sessions: list[BaseSession]) -> list[Insight]:
        """Analyze sessions for cross-source correlations.

        Args:
            sessions: List of sessions to analyze.

        Returns:
            List of insights about cross-session relationships.
        """
        insights: list[Insight] = []

        if len(sessions) < 2:
            return insights

        # Group sessions by source
        by_source: dict[str, list[BaseSession]] = defaultdict(list)
        for session in sessions:
            by_source[session.source].append(session)

        # Analyze source distribution
        insights.extend(self._analyze_source_distribution(by_source))

        # Find related sessions across sources
        insights.extend(self._find_related_sessions(sessions))

        # Identify session chains (sequential related work)
        insights.extend(self._identify_session_chains(sessions))

        # Compare tool usage across sources
        insights.extend(self._compare_source_tools(by_source))

        return insights

    def _analyze_source_distribution(
        self,
        by_source: dict[str, list[BaseSession]],
    ) -> list[Insight]:
        """Analyze how sessions are distributed across sources."""
        insights: list[Insight] = []

        if len(by_source) < 2:
            return insights

        total = sum(len(sessions) for sessions in by_source.values())
        source_percentages = {
            source: len(sessions) / total * 100 for source, sessions in by_source.items()
        }

        primary_source = max(source_percentages, key=lambda k: source_percentages[k])

        insights.append(
            Insight(
                id=self._generate_insight_id("source_distribution"),
                type=InsightType.CROSS_SESSION_CORRELATION,
                title=f"Primary tool: {primary_source}",
                description=(
                    f"Most sessions ({source_percentages[primary_source]:.1f}%) "
                    f"are from {primary_source}. "
                    f"Using {len(by_source)} different coding tools."
                ),
                severity=InsightSeverity.LOW,
                confidence=0.9,
                evidence={
                    "source_counts": {s: len(sessions) for s, sessions in by_source.items()},
                    "source_percentages": source_percentages,
                    "total_sessions": total,
                },
            )
        )

        return insights

    def _find_related_sessions(self, sessions: list[BaseSession]) -> list[Insight]:
        """Find sessions that are related by project or content."""
        insights: list[Insight] = []

        # Group sessions by project (from metadata)
        by_project: dict[str, list[BaseSession]] = defaultdict(list)
        for session in sessions:
            project = session.metadata.get("project")
            if project:
                by_project[project].append(session)

        # Find projects worked on with multiple sources
        for project, project_sessions in by_project.items():
            sources = {s.source for s in project_sessions}
            if len(sources) > 1 and len(project_sessions) >= 3:
                session_ids = [s.id for s in project_sessions][:5]
                insights.append(
                    Insight(
                        id=self._generate_insight_id("multi_source_project", project),
                        type=InsightType.CROSS_SESSION_CORRELATION,
                        title=f"Project '{project}' spans multiple tools",
                        description=(
                            f"Found {len(project_sessions)} sessions for project '{project}' "
                            f"across {len(sources)} different tools: {', '.join(sources)}."
                        ),
                        severity=InsightSeverity.LOW,
                        confidence=0.85,
                        session_ids=session_ids,
                        evidence={
                            "project": project,
                            "session_count": len(project_sessions),
                            "sources": list(sources),
                        },
                    )
                )

        return insights

    def _identify_session_chains(self, sessions: list[BaseSession]) -> list[Insight]:
        """Identify chains of related sequential sessions."""
        insights: list[Insight] = []

        # Sort sessions by start time
        sorted_sessions = sorted(sessions, key=lambda s: s.start_time)

        # Look for sessions that start within 30 minutes of previous ending
        chains: list[list[BaseSession]] = []
        current_chain: list[BaseSession] = []

        for _i, session in enumerate(sorted_sessions):
            if not current_chain:
                current_chain = [session]
                continue

            prev_session = current_chain[-1]
            prev_end = prev_session.end_time or prev_session.start_time

            # Check if this session starts within 30 minutes of previous end
            if (session.start_time - prev_end).total_seconds() < 1800:  # 30 minutes
                current_chain.append(session)
            else:
                if len(current_chain) >= 3:
                    chains.append(current_chain)
                current_chain = [session]

        # Don't forget the last chain
        if len(current_chain) >= 3:
            chains.append(current_chain)

        # Generate insights for significant chains
        for chain in chains:
            chain_duration = (chain[-1].start_time - chain[0].start_time).total_seconds() / 60
            session_ids = [s.id for s in chain]
            sources = {s.source for s in chain}

            insights.append(
                Insight(
                    id=self._generate_insight_id("session_chain", chain[0].id),
                    type=InsightType.CROSS_SESSION_CORRELATION,
                    title=f"Work session chain: {len(chain)} consecutive sessions",
                    description=(
                        f"Found {len(chain)} related sessions "
                        f"spanning {chain_duration:.0f} minutes. "
                        f"This represents a focused work period across {len(sources)} tool(s)."
                    ),
                    severity=InsightSeverity.MEDIUM if len(chain) >= 5 else InsightSeverity.LOW,
                    confidence=0.7,
                    session_ids=session_ids,
                    evidence={
                        "chain_length": len(chain),
                        "total_duration_minutes": chain_duration,
                        "sources": list(sources),
                        "start_time": chain[0].start_time.isoformat(),
                        "end_time": chain[-1].start_time.isoformat(),
                    },
                    recommendations=[
                        "Review what made this focused work period effective",
                    ],
                )
            )

        return insights

    def _compare_source_tools(
        self,
        by_source: dict[str, list[BaseSession]],
    ) -> list[Insight]:
        """Compare tool usage patterns across different sources."""
        insights: list[Insight] = []

        if len(by_source) < 2:
            return insights

        # Count tools per source
        source_tools: dict[str, Counter[str]] = {}
        for source, sessions in by_source.items():
            source_tools[source] = Counter()
            for session in sessions:
                for tool in session.tools_used:
                    source_tools[source][tool.name] += tool.count

        # Find tools unique to certain sources
        all_tools: set[str] = set()
        for tools in source_tools.values():
            all_tools.update(tools.keys())

        for tool in all_tools:
            sources_with_tool = [s for s, t in source_tools.items() if tool in t]
            if len(sources_with_tool) == 1:
                source = sources_with_tool[0]
                count = source_tools[source][tool]
                if count >= 5:
                    insights.append(
                        Insight(
                            id=self._generate_insight_id("unique_tool", tool, source),
                            type=InsightType.TOOL_USAGE_PATTERN,
                            title=f"Tool '{tool}' used only in {source}",
                            description=(
                                f"'{tool}' appears {count} times but only in {source} sessions. "
                                "This might indicate source-specific workflows."
                            ),
                            severity=InsightSeverity.LOW,
                            confidence=0.6,
                            evidence={
                                "tool": tool,
                                "source": source,
                                "count": count,
                            },
                        )
                    )

        return insights


def run_all_analyzers(sessions: list[BaseSession]) -> InsightCollection:
    """Run all pattern analyzers on the given sessions.

    Args:
        sessions: List of sessions to analyze.

    Returns:
        InsightCollection containing all discovered insights.
    """
    analyzers: list[BaseAnalyzer] = [
        SuccessFailureAnalyzer(),
        TimelineAnalyzer(),
        CrossSessionCorrelator(),
    ]

    all_insights: list[Insight] = []
    for analyzer in analyzers:
        insights = analyzer.analyze(sessions)
        all_insights.extend(insights)

    return InsightCollection(
        insights=all_insights,
        sessions_analyzed=len(sessions),
        metadata={
            "analyzers_run": [type(a).__name__ for a in analyzers],
        },
    )
