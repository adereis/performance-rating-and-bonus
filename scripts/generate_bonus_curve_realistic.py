#!/usr/bin/env python3
"""
Bonus Curve Visualization Generator

Generates charts showing the relationship between performance ratings and bonus
payouts based on actual normalization behavior from the bonus calculation algorithm.

Calculates realistic normalization factors based on different team performance
scenarios:

1. All Average (100%): Everyone at target, normalization = 1.0
2. High Performers (120% avg): More raw shares needed, normalization < 1.0
3. Low Performers (80% avg): Fewer raw shares needed, normalization > 1.0
4. Balanced Team: Realistic mix with exceptional performers, normalization ~0.90

Usage:
    python3 generate_bonus_curve_realistic.py

Output:
    docs/bonus-curve-realistic-scenarios.png - Multiple scenario comparison chart

Credits:
    Developed by Claude Code (Anthropic) to align with actual app.py algorithm
"""

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

    Args:
        rating: Performance rating percentage (0-200)
        upside_exp: Exponent for ratings >= 100%
        downside_exp: Exponent for ratings < 100%

    Returns:
        Performance multiplier value
    """
    if rating < 100:
        return (rating / 100) ** downside_exp
    else:
        return (rating / 100) ** upside_exp


def calculate_normalization_factor(team_ratings: List[float]) -> float:
    """
    Calculate the normalization factor for a given team performance distribution.

    This matches the actual algorithm in app.py:
    - Each person has bonus_target (assume 1.0 for simplicity)
    - Calculate raw_share = target * perf_multiplier for each person
    - total_raw_shares = sum of all raw_shares
    - normalization_factor = total_pool / total_raw_shares
    - Since total_pool = sum of targets, and we assume all targets = 1.0:
    - normalization_factor = team_size / total_raw_shares

    Args:
        team_ratings: List of performance ratings for team members

    Returns:
        Normalization factor (value_per_share)
    """
    raw_shares = [calculate_performance_multiplier(r) for r in team_ratings]
    total_raw_shares = sum(raw_shares)
    team_size = len(team_ratings)

    # total_pool = team_size (assuming each person has target = 1.0)
    normalization_factor = team_size / total_raw_shares if total_raw_shares > 0 else 1.0

    return normalization_factor


def generate_realistic_scenarios() -> List[Tuple[str, List[float], str]]:
    """
    Generate realistic team performance scenarios.

    Returns:
        List of (scenario_name, team_ratings, description) tuples
    """
    scenarios = [
        (
            "All Average (100%)",
            [100.0] * 10,
            "Everyone at target\n(normalization = 1.0)"
        ),
        (
            "High Performing Team",
            [120.0] * 10,
            "Everyone 120%\n(normalization < 1.0)"
        ),
        (
            "Low Performing Team",
            [80.0] * 10,
            "Everyone 80%\n(normalization > 1.0)"
        ),
        (
            "Balanced Team",
            [50, 80, 90, 95, 100, 100, 105, 140, 160, 180],
            "Typical team with 3 stars\n(norm ~0.90)"
        ),
        (
            "Bimodal (Stars & Struggles)",
            [60, 65, 70, 75, 80, 130, 135, 140, 145, 150],
            "Two clusters\n(high variance)"
        ),
        (
            "Top Heavy",
            [95, 100, 105, 110, 120, 125, 130, 135, 140, 150],
            "Most above target\n(strong team)"
        )
    ]

    return scenarios


def generate_single_chart_with_realistic_bands(output_file: str) -> None:
    """
    Generate a single chart showing the base curve with realistic normalization bands.

    Uses High Performing Team and Low Performing Team scenarios to show the
    actual range of normalization that occurs in practice.
    """
    # Generate rating values from 0% to 200%
    ratings = np.linspace(RATING_MIN, RATING_MAX, DATA_POINTS)

    # Calculate base performance multipliers
    raw_multipliers = np.array([
        calculate_performance_multiplier(r) for r in ratings
    ])

    # Calculate normalization factors for different realistic scenarios
    high_team_norm = calculate_normalization_factor([120.0] * 10)
    low_team_norm = calculate_normalization_factor([80.0] * 10)
    avg_team_norm = calculate_normalization_factor([100.0] * 10)
    balanced_norm = calculate_normalization_factor([50, 80, 90, 95, 100, 100, 105, 140, 160, 180])

    # Calculate payout percentages for different scenarios
    payout_avg = raw_multipliers * avg_team_norm * 100
    payout_high_team = raw_multipliers * high_team_norm * 100  # Lower normalization
    payout_low_team = raw_multipliers * low_team_norm * 100   # Higher normalization
    payout_balanced = raw_multipliers * balanced_norm * 100

    # Create figure
    plt.figure(figsize=(12, 8))
    plt.style.use('bmh')

    # Add reference grid
    plt.grid(True, which='major', linestyle='-', alpha=0.6)
    plt.axvline(x=100, color='gray', linestyle=':', linewidth=2, alpha=0.5)
    plt.axhline(y=100, color='gray', linestyle=':', linewidth=2, alpha=0.5)

    # Plot linear reference
    plt.plot(ratings, ratings, linestyle='--', color='gray', alpha=0.3,
             label='Linear Reference (1:1)')

    # Plot the realistic payout band (between low and high performing teams)
    plt.fill_between(ratings, payout_high_team, payout_low_team,
                     color='#0056b3', alpha=0.2,
                     label=f'Realistic Range (norm: {low_team_norm:.3f} - {high_team_norm:.3f})')

    # Plot scenario curves
    plt.plot(ratings, payout_avg, color='#0056b3', linewidth=2.5,
             label=f'All Average Team (norm = {avg_team_norm:.3f})', linestyle='-')
    plt.plot(ratings, payout_balanced, color='#00a000', linewidth=2,
             label=f'Balanced Team (norm = {balanced_norm:.3f})', linestyle='-')
    plt.plot(ratings, payout_high_team, color='#cc6600', linewidth=1.5,
             label=f'All High Performers (norm = {high_team_norm:.3f})', linestyle='--')
    plt.plot(ratings, payout_low_team, color='#cc0000', linewidth=1.5,
             label=f'All Low Performers (norm = {low_team_norm:.3f})', linestyle='--')

    # Mark the 100% target point
    plt.scatter([100], [100], color='#0056b3', s=100, zorder=5)

    # Add explanatory text
    plt.text(120, 55,
             "Band shows normalization range:\n"
             "• High performers → lower norm (stretch budget)\n"
             "• Low performers → higher norm (surplus budget)",
             color='#0056b3', fontsize=10, style='italic',
             bbox=dict(facecolor='white', alpha=0.9, edgecolor='#0056b3', linewidth=1.5))

    # Configure axes and labels
    plt.xlim(RATING_MIN, RATING_MAX)
    plt.ylim(RATING_MIN, RATING_MAX)
    plt.title('Bonus Payout with Realistic Normalization Scenarios', fontsize=16, pad=20)
    plt.xlabel('Performance Rating (%)', fontsize=13)
    plt.ylabel('Final Bonus Payout (% of Target)', fontsize=13)
    plt.legend(loc='upper left', fontsize=9)

    # Save the chart
    plt.savefig(output_file, dpi=DPI, bbox_inches='tight')
    print(f"Single chart saved to: {output_file}")
    print(f"\nNormalization factors calculated:")
    print(f"  All Average (100%): {avg_team_norm:.4f}")
    print(f"  All High (120%): {high_team_norm:.4f}")
    print(f"  All Low (80%): {low_team_norm:.4f}")
    print(f"  Balanced Team: {balanced_norm:.4f}")


def generate_scenario_comparison_chart(output_file: str) -> None:
    """
    Generate a multi-panel chart showing different team scenarios side-by-side.
    """
    scenarios = generate_realistic_scenarios()

    # Create figure with subplots
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Bonus Payout Curves: Team Performance Scenarios', fontsize=18, y=0.995)

    axes = axes.flatten()

    # Generate rating values
    ratings = np.linspace(RATING_MIN, RATING_MAX, DATA_POINTS)
    raw_multipliers = np.array([calculate_performance_multiplier(r) for r in ratings])

    for idx, (scenario_name, team_ratings, description) in enumerate(scenarios):
        ax = axes[idx]

        # Calculate normalization for this scenario
        norm_factor = calculate_normalization_factor(team_ratings)
        payout = raw_multipliers * norm_factor * 100

        # Plot
        ax.plot(ratings, ratings, linestyle='--', color='gray', alpha=0.3, label='Linear (1:1)')
        ax.plot(ratings, payout, color='#0056b3', linewidth=2.5, label=f'Norm = {norm_factor:.3f}')

        # Add individual team member markers with size proportional to count
        rating_counts = Counter(team_ratings)
        for rating, count in rating_counts.items():
            perf_mult = calculate_performance_multiplier(rating)
            final_payout = perf_mult * norm_factor * 100
            # Scale marker size by count (base 50, multiply by count)
            size = 50 * count
            ax.scatter([rating], [final_payout], color='#cc0000', s=size, alpha=0.7, zorder=5)

        # Reference lines
        ax.axvline(x=100, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax.axhline(y=100, color='gray', linestyle=':', linewidth=1, alpha=0.5)
        ax.grid(True, alpha=0.4)

        # Labels and title
        ax.set_xlim(RATING_MIN, RATING_MAX)
        ax.set_ylim(RATING_MIN, RATING_MAX)
        ax.set_title(f'{scenario_name}\n{description}', fontsize=11, pad=10)
        ax.set_xlabel('Performance Rating (%)', fontsize=10)
        ax.set_ylabel('Bonus Payout (% of Target)', fontsize=10)
        ax.legend(loc='upper left', fontsize=8)

    plt.tight_layout()
    plt.savefig(output_file, dpi=DPI, bbox_inches='tight')
    print(f"\nScenario comparison chart saved to: {output_file}")
    print("\nScenario normalization factors:")
    for scenario_name, team_ratings, _ in scenarios:
        norm = calculate_normalization_factor(team_ratings)
        avg_rating = np.mean(team_ratings)
        print(f"  {scenario_name:30s}: norm={norm:.4f}, avg_rating={avg_rating:.1f}%")


if __name__ == '__main__':
    print("="*70)
    print("Generating Bonus Curve Scenario Chart")
    print("="*70)
    print("\nUsing parameters:")
    print(f"  Upside exponent: {UPSIDE_EXPONENT}")
    print(f"  Downside exponent: {DOWNSIDE_EXPONENT}")
    print("\n" + "="*70 + "\n")

    # Generate scenario comparison chart
    generate_scenario_comparison_chart('docs/bonus-curve-realistic-scenarios.png')

    print("\n" + "="*70)
    print("Chart generation complete!")
    print("="*70)
