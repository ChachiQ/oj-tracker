import os


class BaseConfig:
    """Base configuration shared across all environments."""

    # Flask core
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-me')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'SQLALCHEMY_DATABASE_URI', 'sqlite:///dev.db'
    )

    # AI provider settings
    AI_PROVIDER = os.environ.get('AI_PROVIDER', 'zhipu')
    AI_MODEL_BASIC = os.environ.get('AI_MODEL_BASIC', 'glm-4-flash')
    AI_MODEL_ADVANCED = os.environ.get('AI_MODEL_ADVANCED', 'glm-4-plus')

    # AI API keys
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
    ZHIPU_API_KEY = os.environ.get('ZHIPU_API_KEY', '')

    # AI budget control
    AI_MONTHLY_BUDGET = float(os.environ.get('AI_MONTHLY_BUDGET', '5.0'))

    # Scraper settings
    SCRAPER_RATE_LIMIT = float(os.environ.get('SCRAPER_RATE_LIMIT', '0.5'))

    # Scheduler
    SCHEDULER_ENABLED = os.environ.get(
        'SCHEDULER_ENABLED', 'false'
    ).lower() in ('true', '1', 'yes')


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'SQLALCHEMY_DATABASE_URI', 'sqlite:///dev.db'
    )
    SCHEDULER_ENABLED = False


class ProductionConfig(BaseConfig):
    """Production environment configuration."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'SQLALCHEMY_DATABASE_URI', 'sqlite:///prod.db'
    )
    SCHEDULER_ENABLED = os.environ.get(
        'SCHEDULER_ENABLED', 'true'
    ).lower() in ('true', '1', 'yes')


class TestingConfig(BaseConfig):
    """Testing environment configuration."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'
    SCHEDULER_ENABLED = False
    SERVER_NAME = 'localhost'


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}
