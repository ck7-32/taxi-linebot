# --- app.py ---
# -*- coding: utf-8 -*-
import os
import logging
import atexit

from flask import Flask, current_app
from pymongo import MongoClient, GEOSPHERE
from apscheduler.schedulers.background import BackgroundScheduler
from linebot import LineBotApi, WebhookHandler

from config import Config

# --- Globals for simplified access ---
# These will be initialized in create_app
db = None
line_bot_api = None
handler = None # WebhookHandler needs to be accessible by webhook_handlers
scheduler = None

# --- Application Factory ---
def create_app(config_class=Config):
    global db, line_bot_api, handler, scheduler

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Setup Logging
    log_level = logging.DEBUG if app.config['DEBUG'] else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s:%(name)s:%(threadName)s:%(message)s')
    logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING) # Quieter scheduler logs

    app.logger.info("Flask App Initializing...")

    # Check Config
    try:
        config_class.check_essential_configs()
    except ValueError as e:
        app.logger.critical(f"Configuration Error: {e}")
        exit(1)

    # Initialize MongoDB
    try:
        client = MongoClient(app.config['MONGO_URI'])
        client.server_info() # Verify connection
        db = client[app.config['MONGO_DB_NAME']]
        app.logger.info(f"Connected to MongoDB: {app.config['MONGO_DB_NAME']}")
        initialize_database(db, app.logger)
    except Exception as e:
        app.logger.critical(f"Failed to connect to MongoDB: {e}")
        db = None # Important to keep it None if failed

    # Initialize Line Bot API & Handler
    try:
        if app.config['LINE_CHANNEL_ACCESS_TOKEN'] and app.config['LINE_CHANNEL_SECRET']:
            line_bot_api = LineBotApi(app.config['LINE_CHANNEL_ACCESS_TOKEN'])
            handler = WebhookHandler(app.config['LINE_CHANNEL_SECRET'])
            app.logger.info("Line Bot API and Handler Initialized.")
        else:
             app.logger.critical("LINE secrets not found in config.")
             line_bot_api = None
             handler = None
    except Exception as e:
        app.logger.critical(f"Failed to initialize Line Bot API/Handler: {e}")
        line_bot_api = None
        handler = None

    # Import and Register Blueprints AFTER globals are set
    from webhook_handlers import webhook_bp
    app.register_blueprint(webhook_bp)
    app.logger.info("Webhook Blueprint registered.")

    # Initialize and Start Scheduler
    from matching_logic import process_pending_matches # Import the job function
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=lambda: run_scheduled_job(app, process_pending_matches),
        trigger="interval",
        minutes=app.config['MATCH_INTERVAL_MINUTES'],
        id="process_matches_job",
        replace_existing=True
    )
    # Only start scheduler if DB and API seem okay? Or let it run and log errors? Let it run for now.
    if db is not None and line_bot_api is not None:
         scheduler.start()
         app.logger.info(f"Scheduler started. Running 'process_matches' every {app.config['MATCH_INTERVAL_MINUTES']} minute(s).")
    else:
        app.logger.warning("Scheduler NOT started due to DB or Line API initialization issues.")

    # Register scheduler shutdown hook
    atexit.register(lambda: shutdown_scheduler())

    # Basic root route for health check
    @app.route('/')
    def index():
        return "Taxi Line Bot Service (Simplified) is Running!"

    return app

# --- Helper Functions ---
def initialize_database(db_instance, logger):
    """Creates collections and indexes if they don't exist."""
    if db_instance is None: return
    try:
        collections = db_instance.list_collection_names()
        if 'users' not in collections:
            # db_instance.create_collection('users') # Creating is implicit on first insert/index
            db_instance.users.create_index([("location", GEOSPHERE)], background=True)
            logger.info("Created Geo index on 'users'.")
        if 'pending_matches' not in collections:
            db_instance.pending_matches.create_index([("timestamp", 1)], background=True)
            logger.info("Created timestamp index on 'pending_matches'.")
        if 'matches' not in collections:
            db_instance.matches.create_index([("group_id", 1)], unique=True, background=True)
            logger.info("Created unique group_id index on 'matches'.")
        # feedbacks collection will be created on first insert
    except Exception as e:
        logger.error(f"Error during database indexing: {e}")

def run_scheduled_job(app_context, job_func):
    """Wrapper to run scheduled job within Flask app context."""
    with app_context.app_context():
        try:
            # Perform DB check again inside context, just in case
            if db is None:
                 current_app.logger.error(f"Scheduled job '{job_func.__name__}' skipped: DB not available.")
                 return
            job_func()
        except Exception as e:
             current_app.logger.exception(f"Exception in scheduled job '{job_func.__name__}': {e}")

def shutdown_scheduler():
    """Gracefully shuts down the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        print("Shutting down scheduler...")
        try:
            scheduler.shutdown()
            print("Scheduler shut down.")
        except Exception as e:
            print(f"Error shutting down scheduler: {e}")

# --- Main Execution ---
if __name__ == '__main__':
    app = create_app()
    # Check essential components after creation
    if db is None or line_bot_api is None or handler is None:
         app.logger.critical("Application failed to initialize essential components. Exiting.")
         exit(1)

    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=app.config['DEBUG'])