#!/usr/bin/env python3
"""
Generate and insert a Clip Lab license key into Supabase.

Requires env vars:
  SUPABASE_URL          — e.g. https://abcdefgh.supabase.co
  SUPABASE_SERVICE_KEY  — service role key (not anon) so RLS is bypassed

Usage:
  # Permanent license with display tag
  python scripts/gen_license.py --user "Dan" --expiry none --tag "FREE FOR PRI"

  # Tester license with expiry date
  python scripts/gen_license.py --user "tester1" --expiry 2026-06-01

  # Print key without inserting (dry run)
  python scripts/gen_license.py --user "test" --dry-run
"""

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request


def generate_key() -> str:
    """CLIP-XXXXXX-XXXXXX-XXXXXX format."""
    parts = [secrets.token_hex(3).upper() for _ in range(3)]
    return 'BISCUIT-' + '-'.join(parts)


def insert_license(key: str, user: str, expiry: str | None, tag: str | None) -> dict:
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    svc = os.environ.get('SUPABASE_SERVICE_KEY', '')
    if not url or not svc:
        print('Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.', file=sys.stderr)
        sys.exit(1)

    body: dict = {'key': key, 'user_name': user}
    if expiry:
        body['expiry'] = expiry
    if tag:
        body['tag'] = tag

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f'{url}/rest/v1/licenses',
        data=data,
        headers={
            'apikey':        svc,
            'Authorization': f'Bearer {svc}',
            'Content-Type':  'application/json',
            'Prefer':        'return=representation',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise Exception(f"HTTP {e.code}: {body}")


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate a Clip Lab license key')
    parser.add_argument('--user',    required=True, help='User name or label')
    parser.add_argument('--expiry',  default='none',
                        help='Expiry date YYYY-MM-DD, or "none" for permanent')
    parser.add_argument('--tag',     default=None,
                        help='Optional display tag shown in the app (e.g. "FREE FOR PRI")')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print the key without inserting into Supabase')
    args = parser.parse_args()

    expiry = None if args.expiry.lower() == 'none' else args.expiry
    key    = generate_key()

    print()
    print(f'  User   : {args.user}')
    print(f'  Expiry : {expiry or "permanent"}')
    if args.tag:
        print(f'  Tag    : {args.tag}')
    print()

    if args.dry_run:
        print('  [dry run — not inserted]')
    else:
        try:
            insert_license(key, args.user, expiry, args.tag)
            print('  Inserted into Supabase ✓')
        except Exception as e:
            print(f'  Error inserting: {e}', file=sys.stderr)
            print('  Key generated but NOT saved:', file=sys.stderr)

    print()
    print('  License key:')
    print(f'  {key}')
    print()


if __name__ == '__main__':
    main()
