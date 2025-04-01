# --- matching_logic.py ---
import logging
import uuid
import time
from threading import Thread
from datetime import datetime, timedelta
from flask import current_app # Use this to access config in scheduled task
import requests 
# Assume db and line_bot_api are initialized in app.py and imported
# This is simpler but relies on global state.
from app import db, line_bot_api
import message_templates # Use the message template functions

logger = logging.getLogger(__name__)

# --- Helper Functions (Moved Here) ---
def get_user_profile(user_id):
     """Attempts to get user's Line display name."""
     if line_bot_api is None: return None
     try:
         profile = line_bot_api.get_profile(user_id)
         return profile.display_name
     except Exception as e:
         logger.warning(f"Failed to get profile for {user_id}: {e}")
         return None

def notify_match_timeout(user_id, timeout_minutes):
    """Notifies user about match timeout."""
    if line_bot_api is None: return
    try:
        message = message_templates.create_timeout_message(timeout_minutes)
        line_bot_api.push_message(user_id, message)
        logger.info(f"Notified user {user_id} about match timeout.")
    except Exception as e:
        logger.error(f"Failed to notify timeout for {user_id}: {e}")


def show_loading_indicator(user_id: str, seconds: int = 30):
    """
    Shows the official LINE loading indicator for the specified user.
    API Ref: https://developers.line.biz/en/docs/messaging-api/use-loading-indicator/

    Args:
        user_id: The target user ID.
        seconds: Duration to show the indicator (5-60 seconds). Defaults to 30.
    """
    if line_bot_api is None:
        logger.error("Cannot show loading indicator: Line Bot API not available.")
        return
    if not (5 <= seconds <= 60):
        logger.warning(f"Loading indicator seconds ({seconds}) out of range (5-60). Using 30.")
        seconds = 30

    api_url = "https://api.line.me/v2/bot/chat/loading/start"
    access_token = current_app.config.get('LINE_CHANNEL_ACCESS_TOKEN') # Get token from config

    if not access_token:
        logger.error("Cannot show loading indicator: Missing LINE_CHANNEL_ACCESS_TOKEN.")
        return

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "chatId": user_id,
        "loadingSeconds": seconds
    }

    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=10) # Added timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        if response.status_code == 202: # 202 Accepted is success for this API
            logger.info(f"Successfully triggered loading indicator for user {user_id} for {seconds}s.")
        else:
            # This part might not be reached if raise_for_status() catches non-2xx codes
            logger.warning(f"Unexpected status code {response.status_code} when showing loading indicator for {user_id}. Body: {response.text}")

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error when trying to show loading indicator for {user_id}.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error showing loading indicator for user {user_id}: {e}")
        # Log response body if available for more details on API errors
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"--> Response status: {e.response.status_code}, body: {e.response.text}")

# --- Core Matching Logic ---
def process_pending_matches():
    """Processes pending matches, run by the scheduler."""
    if db is None:
        logger.error("[Matcher] DB not available, skipping matching.")
        return

    # Use Flask app context to access config reliably
    with current_app.app_context():
        timeout_minutes = current_app.config['MATCH_TIMEOUT_MINUTES']
        precision = current_app.config['DESTINATION_PRECISION']
        logger.info("----- Starting Match Processing -----")

        # 1. Handle Timeouts
        timeout_threshold = datetime.now() - timedelta(minutes=timeout_minutes)
        timed_out_users = list(db.pending_matches.find({'timestamp': {'$lt': timeout_threshold}}))
        if timed_out_users:
            timed_out_ids = [u['line_user_id'] for u in timed_out_users]
            logger.info(f"Found {len(timed_out_ids)} timed out requests: {timed_out_ids}")
            if timed_out_ids:
                db.pending_matches.delete_many({'line_user_id': {'$in': timed_out_ids}})
            for user in timed_out_users:
                notify_match_timeout(user['line_user_id'], timeout_minutes)

        # 2. Get remaining pending users
        pending = list(db.pending_matches.find())
        if not pending:
            logger.info("No pending requests to process.")
            logger.info("----- Match Processing Finished -----")
            return
        logger.info(f"Processing {len(pending)} pending requests.")

        # 3. Group by Destination
        destinations = {}
        for p in pending:
            dest_coords = p.get('destination')
            user_id = p.get('line_user_id')
            if not dest_coords or len(dest_coords) != 2:
                logger.warning(f"User {user_id}'s pending request lacks valid destination, skipping.")
                continue
            try:
                lon, lat = float(dest_coords[0]), float(dest_coords[1])
                dest_key = f"{lon:.{precision}f},{lat:.{precision}f}"
                if dest_key not in destinations: destinations[dest_key] = []
                destinations[dest_key].append(p)
            except (ValueError, TypeError):
                logger.warning(f"User {user_id}'s destination format error: {dest_coords}, skipping.")
                continue

        # 4. Process each destination group
        matched_user_ids_in_cycle = set()
        for dest_key, users_at_dest in destinations.items():
            if len(users_at_dest) < 2: continue

            logger.info(f"Processing destination {dest_key} with {len(users_at_dest)} users.")
            users_at_dest.sort(key=lambda x: x.get('passengers', 1))
            remaining_users_at_dest = users_at_dest.copy()

            while len(remaining_users_at_dest) >= 2:
                # --- Greedy Grouping Logic ---
                potential_group, current_passengers, indices_in_remaining = [], 0, []
                for i, user in enumerate(remaining_users_at_dest):
                    user_passengers = user.get('passengers', 1)
                    if current_passengers + user_passengers <= 4 and len(potential_group) < 4:
                        potential_group.append(user)
                        current_passengers += user_passengers
                        indices_in_remaining.append(i)
                        if len(potential_group) == 4: break
                    elif len(potential_group) < 4 and current_passengers + user_passengers > 4: continue

                # --- Check if group formed ---
                if len(potential_group) >= 2:
                    group_user_ids = [u['line_user_id'] for u in potential_group]
                    logger.info(f"Formed group at {dest_key} ({len(group_user_ids)} users, {current_passengers} passengers): {group_user_ids}")

                    match_id = str(uuid.uuid4())
                    match_data = {
                        'group_id': match_id, 'leader_id': group_user_ids[0],
                        'members': group_user_ids, 'destination_key': dest_key,
                        'destination_coords': potential_group[0]['destination'],
                        'total_passengers': current_passengers,
                        'status': message_templates.MATCH_STATUS_ACTIVE, 'created_at': datetime.now()
                    }
                    try:
                        db.matches.insert_one(match_data)
                        matched_user_ids_in_cycle.update(group_user_ids)
                    except Exception as e:
                        logger.error(f"Failed to save match record {match_id}: {e}")
                        temp_remaining = [user for i, user in enumerate(remaining_users_at_dest) if i not in indices_in_remaining]
                        remaining_users_at_dest = temp_remaining
                        continue

                    # Notify users
                    if line_bot_api:
                        for user_pending_data in potential_group:
                            uid = user_pending_data['line_user_id']
                            profile_name = get_user_profile(uid) or "共乘夥伴"
                            try:
                                message = message_templates.create_match_success_flex(profile_name, len(group_user_ids), match_data)
                                line_bot_api.push_message(uid, message)
                            except Exception as e:
                                logger.error(f"Failed to send match success to {uid}: {e}")

                    # Remove matched users from remaining list
                    temp_remaining = [user for i, user in enumerate(remaining_users_at_dest) if i not in indices_in_remaining]
                    remaining_users_at_dest = temp_remaining

                else: # Cannot form group
                    if remaining_users_at_dest:
                        logger.debug(f"User {remaining_users_at_dest[0]['line_user_id']} at {dest_key} could not form group.")
                        remaining_users_at_dest.pop(0)
                    else: break

        # 5. Remove matched users from pending collection
        if matched_user_ids_in_cycle:
            deleted_count = db.pending_matches.delete_many({'line_user_id': {'$in': list(matched_user_ids_in_cycle)}}).deleted_count
            logger.info(f"Removed {deleted_count} matched users from pending collection.")

        logger.info("----- Match Processing Finished -----")