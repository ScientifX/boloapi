"""
Test Script for BOLO Notification System
Run this to test notifications without running full_refresh

Usage:
    python test_notifications.py [command]

Commands:
    menu              - Interactive menu (default)
    status            - Show pending notifications and opted-in users
    process           - Process and send pending notifications
    add_test          - Add test notification entries
    clear_pending     - Clear all pending notifications (mark as sent)
    clear_all         - Delete all notification log entries
    list_users        - Show all users with notification preferences
    test_email EMAIL  - Send a test notification email to specific address
"""

import sys
import os
from datetime import datetime, date, timezone
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_CONFIG

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


def show_status():
    """Show current notification status"""
    print("\n" + "=" * 60)
    print("NOTIFICATION SYSTEM STATUS")
    print("=" * 60)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Count pending notifications by type
            cur.execute("""
                SELECT change_type, COUNT(*) as count
                FROM tbl_notification_log
                WHERE notified_at IS NULL
                GROUP BY change_type
                ORDER BY change_type
            """)
            pending = cur.fetchall()
            
            print("\nPENDING NOTIFICATIONS:")
            if pending:
                total = 0
                for row in pending:
                    print(f"  {row['change_type']}: {row['count']}")
                    total += row['count']
                print(f"  -----------")
                print(f"  TOTAL: {total}")
            else:
                print("  None")
            
            # Count sent notifications
            cur.execute("""
                SELECT COUNT(*) as count FROM tbl_notification_log
                WHERE notified_at IS NOT NULL
            """)
            sent = cur.fetchone()['count']
            print(f"\nALREADY SENT: {sent}")
            
            # Show opted-in premium users
            cur.execute("""
                SELECT user_id, email, first_name, role,
                       notify_list_changes, notify_status_changes,
                       last_notification_at
                FROM tbl_users
                WHERE role = 'premium'
                  AND is_active = TRUE
                  AND (notify_list_changes = TRUE OR notify_status_changes = TRUE)
                ORDER BY email
            """)
            users = cur.fetchall()
            
            print(f"\nOPTED-IN PREMIUM USERS: {len(users)}")
            for user in users:
                prefs = []
                if user['notify_list_changes']:
                    prefs.append("list")
                if user['notify_status_changes']:
                    prefs.append("status")
                last = user['last_notification_at']
                last_str = last.strftime('%Y-%m-%d %H:%M') if last else 'never'
                print(f"  {user['email']} [{', '.join(prefs)}] (last: {last_str})")


def show_pending_details():
    """Show details of pending notifications"""
    print("\n" + "=" * 60)
    print("PENDING NOTIFICATION DETAILS")
    print("=" * 60)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT log_id, uid, change_type, old_value, new_value,
                       title, detected_at, pull_date
                FROM tbl_notification_log
                WHERE notified_at IS NULL
                ORDER BY detected_at DESC
                LIMIT 50
            """)
            pending = cur.fetchall()
            
            if not pending:
                print("\nNo pending notifications.")
                return
            
            print(f"\nShowing up to 50 most recent:\n")
            for row in pending:
                print(f"  [{row['log_id']}] {row['change_type'].upper()}")
                print(f"      UID: {row['uid']}")
                print(f"      Title: {row['title'] or 'N/A'}")
                if row['old_value'] or row['new_value']:
                    print(f"      Change: {row['old_value']} -> {row['new_value']}")
                print(f"      Detected: {row['detected_at']}")
                print()


def process_notifications():
    """Process and send pending notifications"""
    print("\n" + "=" * 60)
    print("PROCESSING NOTIFICATIONS")
    print("=" * 60)
    
    try:
        from notification_service import process_pending_notifications
        
        print("\nCalling process_pending_notifications()...")
        results = process_pending_notifications()
        
        print("\nRESULTS:")
        print(f"  Users notified: {results.get('users_notified', 0)}")
        print(f"  Emails sent: {results.get('emails_sent', 0)}")
        print(f"  Notifications processed: {results.get('notifications_processed', 0)}")
        
        if results.get('errors'):
            print(f"\nERRORS:")
            for err in results['errors']:
                print(f"  - {err}")
        
    except ImportError as e:
        print(f"\nERROR: Could not import notification_service: {e}")
        print("Make sure notification_service.py is in the project directory.")
    except Exception as e:
        print(f"\nERROR: {e}")


def add_test_notifications():
    """Add test notification entries for testing"""
    print("\n" + "=" * 60)
    print("ADD TEST NOTIFICATIONS")
    print("=" * 60)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get a few real UIDs from tbl_bolo for realistic test data
            cur.execute("""
                SELECT uid, title, poster_url 
                FROM tbl_bolo 
                WHERE is_active = TRUE 
                LIMIT 5
            """)
            records = cur.fetchall()
            
            if not records:
                print("\nNo BOLO records found. Cannot create test notifications.")
                return
            
            today = date.today()
            test_entries = []
            
            # Create one of each type using real data
            if len(records) >= 1:
                r = records[0]
                test_entries.append({
                    'uid': f"TEST-ADDED-{datetime.now().timestamp()}",
                    'change_type': 'added',
                    'old_value': None,
                    'new_value': None,
                    'title': f"[TEST] {r['title']}",
                    'poster_url': r['poster_url'],
                    'pull_date': today
                })
            
            if len(records) >= 2:
                r = records[1]
                test_entries.append({
                    'uid': f"TEST-REMOVED-{datetime.now().timestamp()}",
                    'change_type': 'removed',
                    'old_value': None,
                    'new_value': None,
                    'title': f"[TEST] {r['title']}",
                    'poster_url': r['poster_url'],
                    'pull_date': today
                })
            
            if len(records) >= 3:
                r = records[2]
                test_entries.append({
                    'uid': f"TEST-STATUS-{datetime.now().timestamp()}",
                    'change_type': 'status_change',
                    'old_value': 'na',
                    'new_value': 'captured',
                    'title': f"[TEST] {r['title']}",
                    'poster_url': r['poster_url'],
                    'pull_date': today
                })
            
            if len(records) >= 4:
                r = records[3]
                test_entries.append({
                    'uid': f"TEST-WANTED-{datetime.now().timestamp()}",
                    'change_type': 'most_wanted',
                    'old_value': None,
                    'new_value': 'ten',
                    'title': f"[TEST] {r['title']}",
                    'poster_url': r['poster_url'],
                    'pull_date': today
                })
            
            # Insert test entries
            inserted = 0
            for entry in test_entries:
                try:
                    cur.execute("""
                        INSERT INTO tbl_notification_log 
                            (uid, change_type, old_value, new_value, title, poster_url, pull_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        entry['uid'], entry['change_type'], entry['old_value'],
                        entry['new_value'], entry['title'], entry['poster_url'],
                        entry['pull_date']
                    ))
                    inserted += 1
                    print(f"  Added: {entry['change_type']} - {entry['title']}")
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    print(f"  Skipped (duplicate): {entry['change_type']}")
            
            conn.commit()
            print(f"\nAdded {inserted} test notification entries.")


def clear_pending():
    """Mark all pending notifications as sent"""
    print("\n" + "=" * 60)
    print("CLEAR PENDING NOTIFICATIONS")
    print("=" * 60)
    
    confirm = input("\nMark all pending notifications as sent? (y/N): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE tbl_notification_log
                SET notified_at = NOW()
                WHERE notified_at IS NULL
            """)
            count = cur.rowcount
            conn.commit()
            print(f"\nMarked {count} notifications as sent.")


def clear_all():
    """Delete all notification log entries"""
    print("\n" + "=" * 60)
    print("CLEAR ALL NOTIFICATION LOGS")
    print("=" * 60)
    
    confirm = input("\nDELETE all notification log entries? This cannot be undone! (y/N): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tbl_notification_log")
            count = cur.rowcount
            conn.commit()
            print(f"\nDeleted {count} notification log entries.")


def list_users():
    """List all users with their notification preferences"""
    print("\n" + "=" * 60)
    print("ALL USERS - NOTIFICATION PREFERENCES")
    print("=" * 60)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, email, first_name, role, is_active,
                       notify_list_changes, notify_status_changes,
                       last_notification_at
                FROM tbl_users
                ORDER BY role DESC, email
            """)
            users = cur.fetchall()
            
            print(f"\nTotal users: {len(users)}\n")
            print(f"{'Email':<35} {'Role':<10} {'Active':<8} {'List':<6} {'Status':<8} {'Last Notified'}")
            print("-" * 100)
            
            for user in users:
                list_pref = 'Yes' if user['notify_list_changes'] else 'No'
                status_pref = 'Yes' if user['notify_status_changes'] else 'No'
                active = 'Yes' if user['is_active'] else 'No'
                last = user['last_notification_at']
                last_str = last.strftime('%Y-%m-%d %H:%M') if last else 'Never'
                
                print(f"{user['email']:<35} {user['role']:<10} {active:<8} {list_pref:<6} {status_pref:<8} {last_str}")


def send_test_email(email_address):
    """Send a test notification email to a specific address"""
    print("\n" + "=" * 60)
    print(f"SEND TEST EMAIL TO: {email_address}")
    print("=" * 60)
    
    try:
        from email_utils import send_bolo_notification_email
        
        # Create sample data
        test_additions = [
            {'title': 'John Doe (Test Addition)', 'poster_url': None},
            {'title': 'Jane Smith (Test Addition)', 'poster_url': None}
        ]
        
        test_removals = [
            {'title': 'Bob Wilson (Test Removal)', 'poster_url': None}
        ]
        
        test_status_changes = [
            {'title': 'Alice Brown', 'new_value': 'captured', 'poster_url': None},
            {'title': 'Charlie Davis', 'new_value': 'located', 'poster_url': None}
        ]
        
        test_most_wanted = [
            {'title': 'Eve Johnson (Test Most Wanted)', 'poster_url': None}
        ]
        
        print("\nSending test email with sample data...")
        print(f"  Additions: {len(test_additions)}")
        print(f"  Removals: {len(test_removals)}")
        print(f"  Status changes: {len(test_status_changes)}")
        print(f"  Most Wanted: {len(test_most_wanted)}")
        
        result = send_bolo_notification_email(
            to_email=email_address,
            first_name="Test User",
            additions=test_additions,
            removals=test_removals,
            status_changes=test_status_changes,
            most_wanted=test_most_wanted
        )
        
        if result:
            print(f"\nSUCCESS: Test email sent to {email_address}")
        else:
            print(f"\nFAILED: Could not send email to {email_address}")
            
    except ImportError as e:
        print(f"\nERROR: Could not import email_utils: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")


def interactive_menu():
    """Show interactive menu"""
    while True:
        print("\n" + "=" * 60)
        print("BOLO NOTIFICATION SYSTEM - TEST MENU")
        print("=" * 60)
        print("\n  1. Show status (pending notifications & opted-in users)")
        print("  2. Show pending notification details")
        print("  3. Process and send pending notifications")
        print("  4. Add test notification entries")
        print("  5. Clear pending (mark as sent)")
        print("  6. Clear all notification logs")
        print("  7. List all users with preferences")
        print("  8. Send test email to specific address")
        print("  0. Exit")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            show_status()
        elif choice == '2':
            show_pending_details()
        elif choice == '3':
            process_notifications()
        elif choice == '4':
            add_test_notifications()
        elif choice == '5':
            clear_pending()
        elif choice == '6':
            clear_all()
        elif choice == '7':
            list_users()
        elif choice == '8':
            email = input("Enter email address: ").strip()
            if email:
                send_test_email(email)
        elif choice == '0':
            print("\nGoodbye!")
            break
        else:
            print("\nInvalid choice. Try again.")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        interactive_menu()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'menu':
        interactive_menu()
    elif command == 'status':
        show_status()
    elif command == 'details':
        show_pending_details()
    elif command == 'process':
        process_notifications()
    elif command == 'add_test':
        add_test_notifications()
    elif command == 'clear_pending':
        clear_pending()
    elif command == 'clear_all':
        clear_all()
    elif command == 'list_users':
        list_users()
    elif command == 'test_email':
        if len(sys.argv) < 3:
            print("Usage: python test_notifications.py test_email EMAIL_ADDRESS")
            sys.exit(1)
        send_test_email(sys.argv[2])
    else:
        print(f"Unknown command: {command}")
        print("\nValid commands: menu, status, details, process, add_test, clear_pending, clear_all, list_users, test_email")
        sys.exit(1)


if __name__ == "__main__":
    main()
