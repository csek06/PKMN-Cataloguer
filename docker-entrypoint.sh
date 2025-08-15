#!/bin/bash

# Set default values if not provided
PUID=${PUID:-99}
PGID=${PGID:-100}

echo "Starting with PUID=$PUID, PGID=$PGID"

# Create group if it doesn't exist
if ! getent group $PGID > /dev/null 2>&1; then
    echo "Creating group with GID $PGID"
    groupadd -g $PGID appgroup
else
    echo "Group with GID $PGID already exists"
fi

# Create user if it doesn't exist
if ! getent passwd $PUID > /dev/null 2>&1; then
    echo "Creating user with UID $PUID"
    useradd -u $PUID -g $PGID -d /app -s /bin/bash appuser
else
    echo "User with UID $PUID already exists"
    # Ensure user is in the correct group
    usermod -g $PGID $(getent passwd $PUID | cut -d: -f1)
fi

# Set ownership of data directory to the specified user/group
echo "Setting ownership of /data to $PUID:$PGID"
chown -R $PUID:$PGID /data

# Set ownership of app directory to the specified user/group
echo "Setting ownership of /app to $PUID:$PGID"
chown -R $PUID:$PGID /app

# Run database migrations
echo "Running database migrations..."
gosu $PUID:$PGID python -m migrations.migration_manager

# Execute the command as the specified user
echo "Executing command as UID $PUID, GID $PGID: $@"
exec gosu $PUID:$PGID "$@"
