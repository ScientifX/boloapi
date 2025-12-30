"""
Notification Service Module - BOLO Change Notifications for Premium Users
Handles detection of changes, logging, and sending notification emails.
"""

import logging
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as Connection

from config import DB_CONFIG
from utils_email import send_bolo_notification_email

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Valid status transitions for notifications
# From 'na' (not applicable/unknown) to these statuses triggers notification
NOTIFIABLE_STATUSES = ['captured', 'located', 'recovered', 'resolved', 'surrendered']


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def log_change_if_new(
    conn: Connection,
    uid: str,
    change_type: str,
    old_value: Optional[str],
    new_value: Optional[str],
    title: Optional[str],
    poster_url: Optional[str],
    pull_date: date
) -> bool:
    """
    Attempts to log a change to tbl_notification_log.
    Uses explicit duplicate check to handle NULL values properly.
    
    Args:
        conn: Database connection
        uid: BOLO record UID
        change_type: 'added', 'removed', 'status_change', 'most_wanted'
        old_value: Previous value (None for added)
        new_value: New value (None for removed)
        title: Person name/title for email display
        poster_url: Image URL for email display
        pull_date: Date of the data refresh
    
    Returns:
        bool: True if new change was logged, False if duplicate (already exists)
    """
    # Convert None to empty string for comparison (handles NULL != NULL issue)
    old_val_compare = old_value if old_value is not None else ''
    new_val_compare = new_value if new_value is not None else ''
    
    with conn.cursor() as cur:
        # Check if this exact change already exists (using COALESCE for NULL handling)
        cur.execute("""
            SELECT log_id FROM tbl_notification_log 
            WHERE uid = %s 
              AND change_type = %s 
              AND COALESCE(old_value, '') = %s 
              AND COALESCE(new_value, '') = %s
        """, (uid, change_type, old_val_compare, new_val_compare))
        
        existing = cur.fetchone()
        if existing:
            logger.debug(f"Skipped duplicate change: {change_type} for uid={uid}")
            return False
        
        # Insert new entry
        cur.execute("""
            INSERT INTO tbl_notification_log 
                (uid, change_type, old_value, new_value, title, poster_url, pull_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING log_id
        """, (uid, change_type, old_value, new_value, title, poster_url, pull_date))
        
        result = cur.fetchone()
        if result:
            logger.debug(f"Logged new change: {change_type} for uid={uid}")
            return True
        else:
            logger.debug(f"Failed to log change: {change_type} for uid={uid}")
            return False


def detect_and_log_additions(
    conn: Connection,
    new_uids: List[str],
    records: List[Dict[str, Any]],
    pull_date: date
) -> int:
    """
    Log newly added records (people added to wanted list).
    
    Args:
        conn: Database connection
        new_uids: List of UIDs that were inserted (not updated)
        records: Full record data for looking up titles/posters
        pull_date: Date of the data refresh
    
    Returns:
        int: Number of new additions logged
    """
    if not new_uids:
        return 0
    
    # Build lookup dict for record details
    record_lookup = {r['uid']: r for r in records}
    
    count = 0
    for uid in new_uids:
        record = record_lookup.get(uid, {})
        title = record.get('title', 'Unknown')
        poster_url = record.get('poster_url')
        
        if log_change_if_new(conn, uid, 'added', None, None, title, poster_url, pull_date):
            count += 1
    
    logger.info(f"Logged {count} new additions")
    return count


def detect_and_log_removals(
    conn: Connection,
    removed_uids: List[str],
    pull_date: date
) -> int:
    """
    Log removed records (people no longer on wanted list).
    Now checks both API and web data sources via vw_bolo_full.
    
    Args:
        conn: Database connection
        removed_uids: List of UIDs that were marked inactive
        pull_date: Date of the data refresh
    
    Returns:
        int: Number of removals logged
    """
    if not removed_uids:
        return 0
    
    # Get title and poster_url for removed records (from both sources)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT uid, title, poster_url, data_source
            FROM vw_bolo_full 
            WHERE uid = ANY(%s)
        """, (removed_uids,))
        records = {r['uid']: r for r in cur.fetchall()}
    
    count = 0
    for uid in removed_uids:
        record = records.get(uid, {})
        title = record.get('title', 'Unknown')
        poster_url = record.get('poster_url')
        
        if log_change_if_new(conn, uid, 'removed', None, None, title, poster_url, pull_date):
            count += 1
    
    logger.info(f"Logged {count} removals from both API and web sources")
    return count


def detect_and_log_status_changes(
    conn: Connection,
    records: List[Dict[str, Any]],
    pull_date: date
) -> int:
    """
    Detect and log status changes for existing records.
    Only logs transitions from 'na' to notifiable statuses.
    Now checks both API and web data sources by querying both tables.
    
    Args:
        conn: Database connection
        records: Processed records from current refresh
        pull_date: Date of the data refresh
    
    Returns:
        int: Number of status changes logged
    """
    if not records:
        return 0
    
    uids = [r['uid'] for r in records]
    record_lookup = {r['uid']: r for r in records}
    
    # Get previous status values from BOTH tables
    # We need to check both because vw_bolo_full doesn't have previous_status
    existing_records = {}
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check API table
        cur.execute("""
            SELECT uid, status, previous_status, title, poster_url, 'api' as data_source
            FROM tbl_bolo
            WHERE uid = ANY(%s) AND is_active = TRUE
        """, (uids,))
        for r in cur.fetchall():
            existing_records[r['uid']] = dict(r)
        
        # Check web table (overwrites API if same UID - web takes precedence)
        cur.execute("""
            SELECT uid, status, previous_status, title, poster_url, 'web' as data_source
            FROM tbl_bolo_web
            WHERE uid = ANY(%s) AND is_active = TRUE
        """, (uids,))
        for r in cur.fetchall():
            existing_records[r['uid']] = dict(r)
    
    count = 0
    for uid, new_record in record_lookup.items():
        existing = existing_records.get(uid)
        if not existing:
            continue
        
        old_status = existing.get('status') or 'na'
        new_status = new_record.get('status') or 'na'
        
        # Normalize to lowercase
        old_status_lower = old_status.lower().strip() if old_status else 'na'
        new_status_lower = new_status.lower().strip() if new_status else 'na'
        
        # Check if this is a notifiable status change
        # From 'na' to any of the notifiable statuses
        if old_status_lower == 'na' and new_status_lower in NOTIFIABLE_STATUSES:
            title = new_record.get('title') or existing.get('title', 'Unknown')
            poster_url = new_record.get('poster_url') or existing.get('poster_url')
            
            if log_change_if_new(conn, uid, 'status_change', old_status_lower, new_status_lower, 
                                title, poster_url, pull_date):
                count += 1
                
                # Update the record's previous_status and status_changed_at
                # Update the correct table based on data source
                data_source = existing.get('data_source', 'api')
                table_name = 'tbl_bolo_web' if data_source == 'web' else 'tbl_bolo'
                
                with conn.cursor() as update_cur:
                    update_cur.execute(f"""
                        UPDATE {table_name} 
                        SET previous_status = %s, status_changed_at = NOW()
                        WHERE uid = %s AND is_active = TRUE
                    """, (old_status_lower, uid))
    
    logger.info(f"Logged {count} status changes from both API and web sources")
    return count


def detect_and_log_most_wanted(
    conn: Connection,
    records: List[Dict[str, Any]],
    pull_date: date
) -> int:
    """
    Detect and log when someone becomes Most Wanted (poster_classification = 'ten').
    Now checks both API and web data sources by querying both tables.
    
    Args:
        conn: Database connection
        records: Processed records from current refresh
        pull_date: Date of the data refresh
    
    Returns:
        int: Number of Most Wanted changes logged
    """
    if not records:
        return 0
    
    uids = [r['uid'] for r in records]
    record_lookup = {r['uid']: r for r in records}
    
    # Get previous poster_classification values from BOTH tables
    # We need to check both because vw_bolo_full doesn't have previous_poster_classification
    existing_records = {}
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Check API table
        cur.execute("""
            SELECT uid, poster_classification, previous_poster_classification, 
                   title, poster_url, 'api' as data_source
            FROM tbl_bolo
            WHERE uid = ANY(%s) AND is_active = TRUE
        """, (uids,))
        for r in cur.fetchall():
            existing_records[r['uid']] = dict(r)
        
        # Check web table (overwrites API if same UID - web takes precedence)
        cur.execute("""
            SELECT uid, poster_classification, previous_poster_classification,
                   title, poster_url, 'web' as data_source
            FROM tbl_bolo_web
            WHERE uid = ANY(%s) AND is_active = TRUE
        """, (uids,))
        for r in cur.fetchall():
            existing_records[r['uid']] = dict(r)
    
    count = 0
    for uid, new_record in record_lookup.items():
        existing = existing_records.get(uid)
        if not existing:
            continue
        
        old_classification = existing.get('poster_classification') or ''
        new_classification = new_record.get('poster_classification') or ''
        
        # Normalize to lowercase
        old_class_lower = old_classification.lower().strip() if old_classification else ''
        new_class_lower = new_classification.lower().strip() if new_classification else ''
        
        # Check if this person just became Most Wanted
        if old_class_lower != 'ten' and new_class_lower == 'ten':
            title = new_record.get('title') or existing.get('title', 'Unknown')
            poster_url = new_record.get('poster_url') or existing.get('poster_url')
            
            if log_change_if_new(conn, uid, 'most_wanted', old_class_lower or None, 'ten', 
                                title, poster_url, pull_date):
                count += 1
                
                # Update the record's previous_poster_classification
                # Update the correct table based on data source
                data_source = existing.get('data_source', 'api')
                table_name = 'tbl_bolo_web' if data_source == 'web' else 'tbl_bolo'
                
                with conn.cursor() as update_cur:
                    update_cur.execute(f"""
                        UPDATE {table_name} 
                        SET previous_poster_classification = %s
                        WHERE uid = %s AND is_active = TRUE
                    """, (old_class_lower or None, uid))
    
    logger.info(f"Logged {count} Most Wanted changes from both API and web sources")
    return count


def get_pending_notifications(conn: Connection) -> Dict[str, List[Dict]]:
    """
    Get all pending notifications (notified_at IS NULL), grouped by type.
    
    Returns:
        Dict with keys: 'added', 'removed', 'status_change', 'most_wanted'
        Each value is a list of notification records
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT log_id, uid, change_type, old_value, new_value, 
                   title, poster_url, detected_at, pull_date
            FROM tbl_notification_log
            WHERE notified_at IS NULL
            ORDER BY detected_at ASC
        """)
        
        results = cur.fetchall()
    
    # Group by change type
    grouped = {
        'added': [],
        'removed': [],
        'status_change': [],
        'most_wanted': []
    }
    
    for row in results:
        change_type = row['change_type']
        if change_type in grouped:
            grouped[change_type].append(dict(row))
    
    return grouped


def get_premium_users_for_notifications(conn: Connection) -> List[Dict]:
    """
    Get active PREMIUM users who have opted into at least one notification type.
    
    Returns:
        List of user dicts with email and notification preferences
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT user_id, email, first_name, notify_list_changes, notify_status_changes
            FROM tbl_users
            WHERE role = 'premium'
              AND is_active = TRUE
              AND (notify_list_changes = TRUE OR notify_status_changes = TRUE)
        """)
        
        return [dict(row) for row in cur.fetchall()]


def mark_notifications_sent(conn: Connection, log_ids: List[int]) -> int:
    """
    Mark notifications as sent by setting notified_at timestamp.
    
    Args:
        conn: Database connection
        log_ids: List of notification log IDs to mark
    
    Returns:
        int: Number of records updated
    """
    if not log_ids:
        return 0
    
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE tbl_notification_log
            SET notified_at = NOW()
            WHERE log_id = ANY(%s)
        """, (log_ids,))
        
        count = cur.rowcount
        logger.info(f"Marked {count} notifications as sent")
        return count


def update_user_last_notification(conn: Connection, user_id: str):
    """Update user's last_notification_at timestamp"""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE tbl_users
            SET last_notification_at = NOW()
            WHERE user_id = %s
        """, (user_id,))


def process_pending_notifications() -> Dict[str, Any]:
    """
    Main function to process and send pending notifications.
    
    Process:
    1. Query pending notifications from tbl_notification_log
    2. Get PREMIUM users with notification preferences
    3. For each user, build personalized email based on preferences
    4. Send emails
    5. Mark notifications as sent
    
    Returns:
        Dict with summary: users_notified, emails_sent, notifications_processed
    """
    summary = {
        'users_notified': 0,
        'emails_sent': 0,
        'notifications_processed': 0,
        'errors': []
    }
    
    try:
        with get_db_connection() as conn:
            # Get pending notifications
            pending = get_pending_notifications(conn)
            
            total_pending = sum(len(v) for v in pending.values())
            if total_pending == 0:
                logger.info("No pending notifications to process")
                return summary
            
            logger.info(f"Found {total_pending} pending notifications")
            logger.info(f"  - Added: {len(pending['added'])}")
            logger.info(f"  - Removed: {len(pending['removed'])}")
            logger.info(f"  - Status changes: {len(pending['status_change'])}")
            logger.info(f"  - Most Wanted: {len(pending['most_wanted'])}")
            
            # Get users to notify
            users = get_premium_users_for_notifications(conn)
            
            if not users:
                logger.info("No premium users opted into notifications")
                # Still mark notifications as processed so they don't pile up
                all_log_ids = []
                for change_list in pending.values():
                    all_log_ids.extend([n['log_id'] for n in change_list])
                if all_log_ids:
                    mark_notifications_sent(conn, all_log_ids)
                    summary['notifications_processed'] = len(all_log_ids)
                conn.commit()
                return summary
            
            logger.info(f"Found {len(users)} premium users to potentially notify")
            
            # Track which log_ids we've successfully notified
            notified_log_ids = set()
            
            # Send personalized emails to each user
            for user in users:
                try:
                    # Build notification content based on user preferences
                    user_additions = []
                    user_removals = []
                    user_status_changes = []
                    user_most_wanted = []
                    user_log_ids = []
                    
                    # List changes (additions and removals)
                    if user.get('notify_list_changes'):
                        user_additions = pending['added']
                        user_removals = pending['removed']
                        user_log_ids.extend([n['log_id'] for n in pending['added']])
                        user_log_ids.extend([n['log_id'] for n in pending['removed']])
                    
                    # Status changes (status_change and most_wanted)
                    if user.get('notify_status_changes'):
                        user_status_changes = pending['status_change']
                        user_most_wanted = pending['most_wanted']
                        user_log_ids.extend([n['log_id'] for n in pending['status_change']])
                        user_log_ids.extend([n['log_id'] for n in pending['most_wanted']])
                    
                    # Skip if no notifications for this user's preferences
                    if not any([user_additions, user_removals, user_status_changes, user_most_wanted]):
                        continue
                    
                    # Send email
                    first_name = user.get('first_name') or 'Premium User'
                    success = send_bolo_notification_email(
                        to_email=user['email'],
                        first_name=first_name,
                        additions=user_additions,
                        removals=user_removals,
                        status_changes=user_status_changes,
                        most_wanted=user_most_wanted
                    )
                    
                    if success:
                        summary['users_notified'] += 1
                        summary['emails_sent'] += 1
                        notified_log_ids.update(user_log_ids)
                        update_user_last_notification(conn, user['user_id'])
                        logger.info(f"Sent notification to {user['email']}")
                    else:
                        summary['errors'].append(f"Failed to send to {user['email']}")
                        logger.error(f"Failed to send notification to {user['email']}")
                
                except Exception as e:
                    summary['errors'].append(f"Error for {user.get('email', 'unknown')}: {str(e)}")
                    logger.error(f"Error sending notification to {user.get('email')}: {str(e)}")
            
            # Mark all notified log entries as sent
            if notified_log_ids:
                mark_notifications_sent(conn, list(notified_log_ids))
                summary['notifications_processed'] = len(notified_log_ids)
            
            conn.commit()
            
    except Exception as e:
        summary['errors'].append(f"Process error: {str(e)}")
        logger.error(f"Error processing notifications: {str(e)}")
    
    logger.info(f"Notification processing complete: {summary}")
    return summary


def detect_all_changes(
    conn: Connection,
    processed_records: List[Dict[str, Any]],
    inserted_uids: List[str],
    removed_uids: List[str],
    pull_date: date
) -> Dict[str, int]:
    """
    Main entry point to detect and log all types of changes during a refresh.
    Called from router_etl.py after data is loaded.
    
    Args:
        conn: Database connection
        processed_records: All processed records from current refresh
        inserted_uids: UIDs that were newly inserted (not updated)
        removed_uids: UIDs that were marked inactive (not in current pull)
        pull_date: Date of the data refresh
    
    Returns:
        Dict with counts for each change type
    """
    results = {
        'additions': 0,
        'removals': 0,
        'status_changes': 0,
        'most_wanted': 0
    }
    
    try:
        # Log additions
        results['additions'] = detect_and_log_additions(
            conn, inserted_uids, processed_records, pull_date
        )
        
        # Log removals
        results['removals'] = detect_and_log_removals(
            conn, removed_uids, pull_date
        )
        
        # Log status changes
        results['status_changes'] = detect_and_log_status_changes(
            conn, processed_records, pull_date
        )
        
        # Log Most Wanted changes
        results['most_wanted'] = detect_and_log_most_wanted(
            conn, processed_records, pull_date
        )
        
        logger.info(f"Change detection complete: {results}")
        
    except Exception as e:
        logger.error(f"Error detecting changes: {str(e)}")
        raise
    
    return results
