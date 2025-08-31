#!/bin/bash
# crm/cron_jobs/clean_inactive_customers.sh
# Deletes customers with no orders in the last 365 days and logs the count.

set -euo pipefail

# Go to the repo root (two levels up from crm/cron_jobs)
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"

# If you use a virtualenv, uncomment the next line and set the path:
# source .venv/bin/activate

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

# Run a short Python one-liner inside Django's context via manage.py shell
DELETED_COUNT=$(python manage.py shell -c "
from django.utils import timezone
from datetime import timedelta
from crm.models import Customer

cutoff = timezone.now() - timedelta(days=365)

# Customers that DO NOT have an order within the last year
qs = Customer.objects.exclude(order__order_date__gte=cutoff).distinct()

count = qs.count()
qs.delete()
print(count)
")

echo \"$TIMESTAMP Deleted ${DELETED_COUNT} inactive customers\" >> /tmp/customer_cleanup_log.txt
