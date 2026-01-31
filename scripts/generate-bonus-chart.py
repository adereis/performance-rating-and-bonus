#!/usr/bin/env python3
"""
Generate bonus curve visualization charts for documentation.

Creates charts showing the relationship between performance ratings and bonus
payouts based on the actual normalization behavior from the bonus calculation
algorithm.

Usage:
    python3 scripts/generate-bonus-chart.py                # Generate default chart
    python3 scripts/generate-bonus-chart.py --output FILE  # Custom output path

Output:
    docs/bonus-curve-realistic-scenarios.png (default)
"""

import argparse
import matplotlib.pyplot as plt
import numpy as np
from collections import Counter
from typing import List, Tuple


# Configuration parameters matching app.py bonus calculation defaults
UPSIDE_EXPONENT = 1.35      # Exponent for ratings >= 100%
DOWNSIDE_EXPONENT = 1.9     # Exponent for ratings < 100%

# Chart settings
RATING_MIN = 0              # Minimum performance rating (%)
RATING_MAX = 200            # Maximum performance rating (%)
DATA_POINTS = 400           # Number of points for smooth curve
DPI = 300


def calculate_performance_multiplier(rating: float,
                                     upside_exp: float = UPSIDE_EXPONENT,
                                     downside_exp: float = DOWNSIDE_EXPONENT) -> float:
    """
    Calculate performance multiplier for a given rating.

    Uses split curve approach matching the bonus calculation algorithm:
    - Ratings < 100%: (rating/100)^downside_exponent
    - Ratings >= 100%: (rating/100)^upside_exponent
    """
    if rating < 100:
        return (rating / 100) ** downside_exp
    else:
        return (rating / 100) ** upside_exp


def calculate_normalization_factor(team_ratings: List[float]) -> float:
    """Calculate the normalization factor for a given team performance distribution."""
    raw_shares = [calculate_performance_multiplier(r) for r in team_ratings]
    total_raw_shares = sum(raw_shares)
    team_size = len(team_ratings)
    return team_size / total_raw_shares if total_raw_shares > 0 else 1.0


def generate_realistic_scenarios() -> List[Tuple[str, List[float], str]]:
    """Generate realistic team performance scenarios."""
    return [
        ("All Average (100%)", [100.0] * 10, "Everyone at target\n(normalization = 1.0)"),
        ("High Performing Team", [120.0] * 10, "Everyone 120%\n(normalization < 1.0)"),
        ("Low Performing Team", [80.0] * 10, "Everyone 80%\n(normalization > 1.0)"),
        ("Balanced Team", [50, 80, 90, 95, 100, 100, 105, 140, 160, 180], "Typical team with 3 stars\n(norm ~0.90)"),
        ("Bimodal (Stars & Struggles)", [60, 65, 70, 75, 80, 130, 135, 140, 145, 150], "Two clusters\n(high variance)"),
        ("Top Heavy", [95, 100, 105, 110, 120, 125, 130, 135, 140, 150], "Most above target\n(strong team)")
    ]


def generate_scenario_comparison_chart(output_file: str) -> None:
    """Generate a multi-panel chart showing different team scenarios side-by-side."""
    scenarios = generate_realistic_scenarios()

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Bonus Payout Curves: Team Performance Scenarios', fontsize=18, y=0.995)

    axes = axes.flatten()

    ratings = np.linspace(RATING_MIN, RATING_MAX, DATA_POINTS)
    raw_multipliers = np.array([calculate_performance_multiplier(r) for r in ratings])

    for idx, (scenario_name, team_ratings, description) in enumerate(scenarios):
        ax = axes[idx]

        norm_factor = calculate_normalization_factor(team_ratings)
        payout = raw_multipliers * norm_factor * 100

        ax.plot(ratings, ratings, linestyle='--', color='gray', alpha=0.3, label='Linear (1:1)')
        ax.plot(ratings, payout, color='#0056b3', linewidth=2.5, label=f'Norm = {norm_factor:.3f}')

        rating_counts = Counter(team_ratings)
        for rating, count in rating_counts.items():
            perf_mult = calculate_performance_multiplier(rating)
            final_payout = perf_mult * norm_factor * 100
            size = 50 * count
            ax.scatter([rating], [final_payout], color='#cc0000', s=size, alpha=0.7, zorder=5)

        ax.axvline(x=100, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax.axhline(y=100, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax.grid(True, alpha=0.4)

        ax.set_xlim(RATING_MIN, RATING_MAX)
        ax.set_ylim(RATING_MIN, RATING_MAX)
        ax.set_title(f'{scenario_name}\n{description}', fontsize=11, pad=10)
        ax.set_xlabel('Performance Rating (%)', fontsize=10)
        ax.set_ylabel('Bonus Payout (% of Target)', fontsize=10)
        ax.legend(loc='upper left', fontsize=8)

    plt.tight_layout()
    plt.savefig(output_file, dpi=DPI, bbox_inches='tight')

    print(f"✓ Created {output_file}")
    print(f"\nScenario normalization factors:")
    for scenario_name, team_ratings, _ in scenarios:
        norm = calculate_normalization_factor(team_ratings)
        avg_rating = np.mean(team_ratings)
        print(f"  {scenario_name:30s}: norm={norm:.4f}, avg_rating={avg_rating:.1f}%")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Generate bonus curve visualization charts for documentation.',
        epilog='''
Examples:
  %(prog)s                                    # Generate default chart
  %(prog)s --output my-chart.png              # Custom output path

The chart shows how bonus payouts vary with performance ratings under
different team normalization scenarios.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--output', '-o', type=str,
                        default='docs/bonus-curve-realistic-scenarios.png',
                        help='Output file path (default: docs/bonus-curve-realistic-scenarios.png)')

    args = parser.parse_args()

    print("=" * 60)
    print("Generating Bonus Curve Chart")
    print("=" * 60)
    print(f"\nParameters:")
    print(f"  Upside exponent: {UPSIDE_EXPONENT}")
    print(f"  Downside exponent: {DOWNSIDE_EXPONENT}")
    print()

    generate_scenario_comparison_chart(args.output)


if __name__ == '__main__':
    main()
