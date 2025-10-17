#!/usr/bin/env python3
"""Command-line tool for managing newsletter subscribers.

Provides commands for listing, adding, removing, and exporting subscribers
from the SES contact list.
"""

import boto3
import argparse
import sys
from tabulate import tabulate

ses_v2 = boto3.client('sesv2', region_name='us-east-1')
CONTACT_LIST = 'iridia-daily-subscribers'


def list_contacts(status=None):
    """List all contacts, optionally filtered by subscription status.
    
    Args:
        status: Optional filter for subscription status (OPT_IN or OPT_OUT)
    """
    contacts = []
    paginator = ses_v2.get_paginator('list_contacts')
    
    for page in paginator.paginate(ContactListName=CONTACT_LIST):
        for contact in page.get('Contacts', []):
            topic_prefs = contact.get('TopicPreferences', [{}])[0]
            sub_status = topic_prefs.get('SubscriptionStatus', 'UNKNOWN')
            
            if status and sub_status != status:
                continue
            
            contacts.append([
                contact['EmailAddress'],
                sub_status,
                str(contact.get('CreatedTimestamp', 'N/A'))[:10]
            ])
    
    if not contacts:
        print(f"No contacts found{f' with status: {status}' if status else ''}")
        return
    
    print(f"\nTotal: {len(contacts)} contacts")
    print(tabulate(contacts, headers=['Email', 'Status', 'Created'], tablefmt='grid'))


def get_stats():
    """Display subscription statistics."""
    opted_in = opted_out = 0
    paginator = ses_v2.get_paginator('list_contacts')
    
    for page in paginator.paginate(ContactListName=CONTACT_LIST):
        for contact in page.get('Contacts', []):
            status = contact.get('TopicPreferences', [{}])[0].get('SubscriptionStatus')
            if status == 'OPT_IN':
                opted_in += 1
            elif status == 'OPT_OUT':
                opted_out += 1
    
    total = opted_in + opted_out
    print("\n=== Iridia Daily Subscriber Statistics ===")
    print(f"Total Contacts: {total}")
    print(f"  Active Subscribers: {opted_in}")
    print(f"  Unsubscribed: {opted_out}\n")


def add_contact(email):
    """Add a new subscriber.
    
    Args:
        email: Email address to add
    """
    try:
        ses_v2.create_contact(
            ContactListName=CONTACT_LIST,
            EmailAddress=email.lower(),
            TopicPreferences=[{
                'TopicName': 'daily-research',
                'SubscriptionStatus': 'OPT_IN'
            }]
        )
        print(f"✓ Added {email}")
    except ses_v2.exceptions.AlreadyExistsException:
        print(f"✗ {email} already exists")
    except Exception as e:
        print(f"✗ Error: {e}")


def remove_contact(email):
    """Remove a subscriber.
    
    Args:
        email: Email address to remove
    """
    try:
        ses_v2.delete_contact(
            ContactListName=CONTACT_LIST,
            EmailAddress=email.lower()
        )
        print(f"✓ Removed {email}")
    except ses_v2.exceptions.NotFoundException:
        print(f"✗ {email} not found")
    except Exception as e:
        print(f"✗ Error: {e}")


def export_contacts(status='OPT_IN', filename='subscribers.txt'):
    """Export subscriber email addresses to a file.
    
    Args:
        status: Subscription status to export (OPT_IN or OPT_OUT)
        filename: Output file path
    """
    emails = []
    paginator = ses_v2.get_paginator('list_contacts')
    
    for page in paginator.paginate(ContactListName=CONTACT_LIST):
        for contact in page.get('Contacts', []):
            topic_prefs = contact.get('TopicPreferences', [{}])[0]
            if topic_prefs.get('SubscriptionStatus') == status:
                emails.append(contact['EmailAddress'])
    
    with open(filename, 'w') as f:
        f.write('\n'.join(emails))
    
    print(f"✓ Exported {len(emails)} {status} contacts to {filename}")


def main():
    """Parse command-line arguments and execute requested command."""
    parser = argparse.ArgumentParser(
        description='Manage Iridia Daily subscribers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s list --status OPT_IN
  %(prog)s stats
  %(prog)s add user@example.com
  %(prog)s remove user@example.com
  %(prog)s export --output subscribers.txt
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all contacts')
    list_parser.add_argument('--status', choices=['OPT_IN', 'OPT_OUT'],
                            help='Filter by subscription status')
    
    # Stats command
    subparsers.add_parser('stats', help='Show subscription statistics')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new subscriber')
    add_parser.add_argument('email', help='Email address to add')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a subscriber')
    remove_parser.add_argument('email', help='Email address to remove')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export subscribers to file')
    export_parser.add_argument('--status', default='OPT_IN',
                              choices=['OPT_IN', 'OPT_OUT'],
                              help='Status to export (default: OPT_IN)')
    export_parser.add_argument('--output', default='subscribers.txt',
                              help='Output filename (default: subscribers.txt)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'list':
        list_contacts(args.status)
    elif args.command == 'stats':
        get_stats()
    elif args.command == 'add':
        add_contact(args.email)
    elif args.command == 'remove':
        remove_contact(args.email)
    elif args.command == 'export':
        export_contacts(args.status, args.output)


if __name__ == '__main__':
    main()