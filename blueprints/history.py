"""History blueprint: period archiving and historical comparison.

Routes: /history, /api/archive-period, /api/periods, /api/period/<id>,
/api/period-comparison/<id>.

Moved verbatim from app.py (docs/REFACTOR_APP_SPLIT.md, Phase 3). get_db is
resolved via the models module so test fixtures patching it are honored.
"""
import json
from datetime import datetime

from flask import Blueprint, render_template, request, jsonify

import models
from models import Employee, Period, RatingSnapshot

from services import db_helpers

history_bp = Blueprint('history', __name__)


@history_bp.route('/history')
def history_page():
    """Period history browser page."""
    db = models.get_db()
    try:
        periods = db.query(Period).order_by(Period.archived_at.desc()).all()

        period_data = []
        for period in periods:
            # Get snapshots for this period
            snapshots = db.query(RatingSnapshot).filter(
                RatingSnapshot.period_id == period.id
            ).all()

            # Calculate stats
            ratings = [s.performance_rating for s in snapshots if s.performance_rating is not None]
            avg_rating = sum(ratings) / len(ratings) if ratings else None
            full_details_count = sum(1 for s in snapshots if s.has_full_details)

            period_data.append({
                'id': period.id,
                'period_id': period.id,
                'name': period.name,
                'archived_at': period.archived_at.strftime('%Y-%m-%d') if period.archived_at else 'Unknown',
                'snapshot_count': len(snapshots),
                'avg_rating': avg_rating,
                'full_details_count': full_details_count
            })

        return render_template('history.html', periods=period_data)

    finally:
        db.close()


@history_bp.route('/api/archive-period', methods=['POST'])
def archive_period():
    """
    Archive the current period's ratings to historical snapshots.

    Creates a Period record and RatingSnapshot for each rated employee.
    Clears all ratings after successful archive.
    """
    data = request.get_json()
    period_id = data.get('period_id', '').strip()
    period_name = data.get('period_name', '').strip()
    notes = data.get('notes', '').strip()

    if not period_id or not period_name:
        return jsonify({'success': False, 'error': 'Period ID and name are required'}), 400

    # Load tenets config for converting IDs to names
    _, tenets_map = db_helpers.load_tenets_config()

    db = models.get_db()
    try:
        # Check if period already exists
        existing_period = db.query(Period).filter(Period.id == period_id).first()
        if existing_period:
            return jsonify({
                'success': False,
                'error': f'Period "{period_id}" already exists. Choose a different ID or delete the existing period first.'
            }), 400

        # Create period
        period = Period(
            id=period_id,
            name=period_name,
            notes=notes if notes else None,
            archived_at=datetime.now()
        )
        db.add(period)

        # Get all employees
        employees = db.query(Employee).all()
        archived_count = 0
        skipped_unrated = 0

        for emp in employees:
            # Skip unrated employees
            if emp.performance_rating_percent is None:
                skipped_unrated += 1
                continue

            # Convert tenet IDs to human-readable names
            strengths_names = None
            improvements_names = None

            if emp.tenets_strengths:
                try:
                    strength_ids = json.loads(emp.tenets_strengths)
                    strength_names_list = [tenets_map.get(tid, tid) for tid in strength_ids]
                    strengths_names = ', '.join(strength_names_list)
                except (json.JSONDecodeError, TypeError):
                    strengths_names = emp.tenets_strengths  # Keep as-is if not valid JSON

            if emp.tenets_improvements:
                try:
                    improvement_ids = json.loads(emp.tenets_improvements)
                    improvement_names_list = [tenets_map.get(tid, tid) for tid in improvement_ids]
                    improvements_names = ', '.join(improvement_names_list)
                except (json.JSONDecodeError, TypeError):
                    improvements_names = emp.tenets_improvements  # Keep as-is if not valid JSON

            # Create snapshot
            snapshot = RatingSnapshot(
                period_id=period_id,
                associate_id=emp.associate_id,
                performance_rating=emp.performance_rating_percent,
                bonus_allocation=None,  # Could calculate if needed
                justification=emp.justification,
                tenets_strengths=strengths_names,
                tenets_improvements=improvements_names,
                mentors=emp.mentor,
                mentees=emp.mentees,
                snapshot_name=emp.associate,
                snapshot_org=emp.supervisory_organization,
                snapshot_job_profile=emp.current_job_profile,
                snapshot_bonus_target_manager_currency=emp.bonus_target_manager_currency or emp.bonus_target_local_currency,
                archived_at=datetime.now(),
                has_full_details=True
            )
            db.add(snapshot)
            archived_count += 1

        # Clear ratings from all employees
        for emp in employees:
            emp.performance_rating_percent = None
            emp.justification = ''
            emp.mentor = ''
            emp.mentees = ''
            emp.tenets_strengths = None
            emp.tenets_improvements = None
            emp.last_updated = None

        db.commit()

        return jsonify({
            'success': True,
            'archived_count': archived_count,
            'skipped_unrated': skipped_unrated,
            'period_id': period_id
        })

    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@history_bp.route('/api/periods')
def list_periods():
    """
    List all archived periods.

    Returns list of periods with basic stats.
    """
    db = models.get_db()
    try:
        periods = db.query(Period).order_by(Period.archived_at.desc()).all()

        result = []
        for period in periods:
            # Count snapshots for this period
            snapshot_count = db.query(RatingSnapshot).filter(
                RatingSnapshot.period_id == period.id
            ).count()

            result.append({
                'id': period.id,
                'name': period.name,
                'notes': period.notes,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None,
                'snapshot_count': snapshot_count
            })

        return jsonify({
            'success': True,
            'periods': result
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@history_bp.route('/api/period/<period_id>')
def get_period_detail(period_id):
    """
    Get detailed information about a specific archived period.

    Returns period info, all snapshots, and statistics.
    """
    db = models.get_db()
    try:
        # Get period
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            return jsonify({'success': False, 'error': f'Period "{period_id}" not found'}), 404

        # Get all snapshots for this period
        snapshots = db.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == period_id
        ).order_by(RatingSnapshot.performance_rating.desc().nullslast()).all()

        # Build snapshot data
        snapshot_data = []
        ratings = []
        full_details_count = 0
        partial_count = 0

        for snap in snapshots:
            snapshot_data.append({
                'associate_id': snap.associate_id,
                'snapshot_name': snap.snapshot_name,
                'snapshot_job_profile': snap.snapshot_job_profile,
                'snapshot_org': snap.snapshot_org,
                'performance_rating': snap.performance_rating,
                'bonus_allocation': snap.bonus_allocation,
                'justification': snap.justification,
                'tenets_strengths': snap.tenets_strengths,
                'tenets_improvements': snap.tenets_improvements,
                'has_full_details': snap.has_full_details
            })

            if snap.performance_rating is not None:
                ratings.append(snap.performance_rating)

            if snap.has_full_details:
                full_details_count += 1
            else:
                partial_count += 1

        # Calculate statistics
        stats = {
            'total_employees': len(snapshots),
            'avg_rating': round(sum(ratings) / len(ratings), 1) if ratings else None,
            'min_rating': min(ratings) if ratings else None,
            'max_rating': max(ratings) if ratings else None,
            'full_details': full_details_count,
            'partial': partial_count
        }

        return jsonify({
            'success': True,
            'period': {
                'id': period.id,
                'period_id': period.id,
                'name': period.name,
                'notes': period.notes,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None
            },
            'snapshots': snapshot_data,
            'stats': stats
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@history_bp.route('/api/period-comparison/<period_id>')
def period_comparison(period_id):
    """
    Compare current ratings with a historical period.

    Returns employees with both current and historical ratings,
    showing who improved, declined, or stayed stable.
    """
    db = models.get_db()
    try:
        # Verify period exists
        period = db.query(Period).filter(Period.id == period_id).first()
        if not period:
            return jsonify({'success': False, 'error': f'Period "{period_id}" not found'}), 404

        # Get all current employees with ratings
        employees = db.query(Employee).all()
        current_ratings = {
            emp.associate_id: {
                'name': emp.associate,
                'rating': emp.performance_rating_percent,
                'job_profile': emp.current_job_profile,
                'org': emp.supervisory_organization
            }
            for emp in employees
        }

        # Get historical snapshots for this period
        snapshots = db.query(RatingSnapshot).filter(
            RatingSnapshot.period_id == period_id
        ).all()
        historical_ratings = {
            snap.associate_id: {
                'rating': snap.performance_rating,
                'name': snap.snapshot_name,
                'job_profile': snap.snapshot_job_profile,
                'org': snap.snapshot_org
            }
            for snap in snapshots
        }

        # Build comparison data
        comparison = []
        improved_count = 0
        declined_count = 0
        stable_count = 0
        new_employees = 0
        departed_employees = 0

        # Employees who exist in current data
        for assoc_id, current in current_ratings.items():
            historical = historical_ratings.get(assoc_id)

            if historical and historical.get('rating') is not None:
                current_rating = current.get('rating')
                historical_rating = historical.get('rating')

                if current_rating is not None:
                    change = current_rating - historical_rating
                    change_pct = round((change / historical_rating * 100), 1) if historical_rating else 0

                    if change > 5:
                        trend = 'improved'
                        improved_count += 1
                    elif change < -5:
                        trend = 'declined'
                        declined_count += 1
                    else:
                        trend = 'stable'
                        stable_count += 1

                    comparison.append({
                        'associate_id': assoc_id,
                        'name': current.get('name'),
                        'job_profile': current.get('job_profile'),
                        'current_rating': current_rating,
                        'historical_rating': historical_rating,
                        'change': round(change, 1),
                        'change_pct': change_pct,
                        'trend': trend
                    })
            else:
                # New employee (not in historical period)
                if current.get('rating') is not None:
                    new_employees += 1
                    comparison.append({
                        'associate_id': assoc_id,
                        'name': current.get('name'),
                        'job_profile': current.get('job_profile'),
                        'current_rating': current.get('rating'),
                        'historical_rating': None,
                        'change': None,
                        'change_pct': None,
                        'trend': 'new'
                    })

        # Employees who left (in historical but not current)
        for assoc_id, historical in historical_ratings.items():
            if assoc_id not in current_ratings:
                departed_employees += 1
                comparison.append({
                    'associate_id': assoc_id,
                    'name': historical.get('name'),
                    'job_profile': historical.get('job_profile'),
                    'current_rating': None,
                    'historical_rating': historical.get('rating'),
                    'change': None,
                    'change_pct': None,
                    'trend': 'departed'
                })

        # Sort by change (largest improvement first), with None values at end
        comparison.sort(key=lambda x: (
            x['change'] is None,
            -(x['change'] or 0)
        ))

        # Calculate summary stats
        current_avg = None
        historical_avg = None
        current_ratings_list = [c['current_rating'] for c in comparison if c['current_rating'] is not None and c['trend'] != 'new']
        historical_ratings_list = [c['historical_rating'] for c in comparison if c['historical_rating'] is not None and c['trend'] != 'departed']

        if current_ratings_list:
            current_avg = round(sum(current_ratings_list) / len(current_ratings_list), 1)
        if historical_ratings_list:
            historical_avg = round(sum(historical_ratings_list) / len(historical_ratings_list), 1)

        return jsonify({
            'success': True,
            'period': {
                'id': period.id,
                'name': period.name,
                'archived_at': period.archived_at.isoformat() if period.archived_at else None
            },
            'comparison': comparison,
            'summary': {
                'improved': improved_count,
                'declined': declined_count,
                'stable': stable_count,
                'new_employees': new_employees,
                'departed_employees': departed_employees,
                'current_avg': current_avg,
                'historical_avg': historical_avg,
                'avg_change': round(current_avg - historical_avg, 1) if current_avg and historical_avg else None
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

