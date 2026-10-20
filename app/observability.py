"""
Module d'observabilité corrigé pour Plant Care API
Version avec support complet OpenTelemetry pour les traces
"""
import logging
import time
import os
import inspect
from typing import Optional
from functools import wraps
from contextlib import contextmanager
from contextvars import ContextVar
from fastapi import FastAPI, Request

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from prometheus_client import Counter, Histogram, Gauge
import structlog

user_registrations_counter = None
plant_creations_counter = None
care_requests_counter = None
comments_counter = None
active_users_gauge = None
plants_in_care_gauge = None

# one value per request: a plain attribute was shared by every concurrent request
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)

class ObservabilityManager:
    """Gestionnaire d'observabilité avec support complet OpenTelemetry"""

    def __init__(self):
        self.logger = structlog.get_logger()
        self.tracer_provider: Optional[TracerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.tracer = None

    def initialize(self, app: FastAPI):
        """Initialise l'observabilité pour l'application"""
        try:
            print("Initializing full observability stack with OpenTelemetry...")
            
            self.setup_logging()
            self.setup_opentelemetry()
            self.setup_custom_metrics() 
            self.setup_auto_instrumentation(app)
            self.setup_middleware(app)
            
            print("Full observability stack initialized successfully!")

        except Exception as e:
            print(f"Warning: Could not initialize full observability stack: {e}")
            print("Continuing with basic logging only...")
            self.setup_basic_logging()

    def setup_logging(self):
        """Configure le logging structuré"""
        try:
            structlog.configure(
                processors=[
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.add_log_level,
                    structlog.processors.JSONRenderer()
                ],
                wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
                logger_factory=structlog.PrintLoggerFactory(),
                cache_logger_on_first_use=True,
            )
            print("Structured logging configured successfully")
        except Exception as e:
            print(f"Warning: Could not setup structured logging: {e}")
            self.setup_basic_logging()

    def setup_basic_logging(self):
        """Configure un logging basique en cas d'échec"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    def setup_opentelemetry(self):
        """Configure OpenTelemetry pour les traces et métriques"""
        try:
            resource = Resource.create({
                ResourceAttributes.SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "plant-care-api"),
                ResourceAttributes.SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
                ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "development"),
            })

            self.tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(self.tracer_provider)

            otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4317")
            print(f"Configuring OTLP trace exporter with endpoint: {otlp_endpoint}")
            
            otlp_span_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                insecure=True,
                headers={}
            )

            span_processor = BatchSpanProcessor(otlp_span_exporter)
            self.tracer_provider.add_span_processor(span_processor)

            self.tracer = trace.get_tracer(__name__)

            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=otlp_endpoint,
                insecure=True,
                headers={}
            )

            metric_reader = PeriodicExportingMetricReader(
                exporter=otlp_metric_exporter,
                export_interval_millis=15000,  # 15 secondes
            )

            self.meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[metric_reader]
            )
            metrics.set_meter_provider(self.meter_provider)

            print("OpenTelemetry configured successfully")

        except Exception as e:
            print(f"Warning: Could not setup OpenTelemetry: {e}")
            self.tracer = None

    def setup_auto_instrumentation(self, app: FastAPI):
        """Configure l'instrumentation automatique"""
        try:
            FastAPIInstrumentor.instrument_app(app)
            print("FastAPI auto-instrumentation enabled")

            SQLAlchemyInstrumentor().instrument()
            print("SQLAlchemy auto-instrumentation enabled")

            RequestsInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            print("HTTP clients auto-instrumentation enabled")

        except Exception as e:
            print(f"Warning: Could not setup auto-instrumentation: {e}")

    def setup_custom_metrics(self):
        """Configure les métriques personnalisées pour l'application"""
        global user_registrations_counter, plant_creations_counter, care_requests_counter
        global comments_counter, active_users_gauge, plants_in_care_gauge

        try:
            user_registrations_counter = Counter(
                'plant_care_user_registrations_total',
                'Number of user registrations',
                ['user_type']
            )

            plant_creations_counter = Counter(
                'plant_care_plant_creations_total',
                'Number of plants created',
                ['owner_type']
            )

            care_requests_counter = Counter(
                'plant_care_care_requests_total',
                'Number of care requests',
                ['action']
            )

            comments_counter = Counter(
                'plant_care_comments_created_total',
                'Number of comments created'
            )

            active_users_gauge = Gauge(
                'plant_care_active_users',
                'Number of currently active users'
            )

            plants_in_care_gauge = Gauge(
                'plant_care_plants_in_care',
                'Number of plants currently in care'
            )

            print("Custom Prometheus metrics configured successfully")

        except Exception as e:
            print(f"Warning: Could not setup custom metrics: {e}")

    def setup_middleware(self, app: FastAPI):
        """Configure les middlewares d'observabilité"""

        @app.middleware("http")
        async def observability_middleware(request: Request, call_next):
            start_time = time.time()

            user_context = {"user_id": self.current_user_id} if self.current_user_id else {}

            self.logger.info(
                "request_started",
                method=request.method,
                url=str(request.url),
                client_ip=request.client.host if request.client else "unknown",
                **user_context
            )

            try:
                response = await call_next(request)

                duration = time.time() - start_time

                self.logger.info(
                    "request_completed",
                    method=request.method,
                    url=str(request.url),
                    status_code=response.status_code,
                    duration_ms=round(duration * 1000, 2),
                    **user_context
                )

                response.headers["X-Process-Time"] = str(duration)
                return response

            except Exception as e:
                process_time = time.time() - start_time

                # Log de l'erreur
                self.logger.error(
                    "request_failed",
                    method=request.method,
                    url=str(request.url),
                    error=str(e),
                    duration_ms=round(process_time * 1000, 2),
                    **user_context
                )
                raise

    def record_user_registration(self, user_type: str = "regular"):
        """Enregistre une inscription d'utilisateur"""
        try:
            if user_registrations_counter:
                user_registrations_counter.labels(user_type=user_type).inc()
        except Exception as e:
            print(f"Error recording user registration metric: {e}")

    def record_plant_creation(self, owner_type: str = "regular"):
        """Enregistre la création d'une plante"""
        try:
            if plant_creations_counter:
                plant_creations_counter.labels(owner_type=owner_type).inc()
        except Exception as e:
            print(f"Error recording plant creation metric: {e}")

    def record_care_request(self, action: str):
        """Enregistre une demande de soin"""
        try:
            if care_requests_counter:
                care_requests_counter.labels(action=action).inc()
        except Exception as e:
            print(f"Error recording care request metric: {e}")

    def record_comment_creation(self):
        """Enregistre la création d'un commentaire"""
        try:
            if comments_counter:
                comments_counter.inc()
        except Exception as e:
            print(f"Error recording comment creation metric: {e}")

    def update_active_users(self, count: int):
        """Met à jour le nombre d'utilisateurs actifs"""
        try:
            if active_users_gauge:
                active_users_gauge.set(count)
        except Exception as e:
            print(f"Error updating active users metric: {e}")

    def update_plants_in_care(self, count: int):
        """Met à jour le nombre de plantes en soin"""
        try:
            if plants_in_care_gauge:
                plants_in_care_gauge.set(count)
        except Exception as e:
            print(f"Error updating plants in care metric: {e}")

    @property
    def current_user_id(self) -> Optional[str]:
        return _current_user_id.get()

    @current_user_id.setter
    def current_user_id(self, user_id: Optional[str]):
        _current_user_id.set(user_id)

    def set_current_user(self, user_id: str):
        """Définit l'utilisateur courant pour le contexte"""
        self.current_user_id = user_id
        if self.tracer:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("user.id", user_id)

    def clear_current_user(self):
        """Efface l'utilisateur courant du contexte"""
        self.current_user_id = None

    @contextmanager
    def user_context(self, user_id: str):
        """Context manager pour définir temporairement un utilisateur"""
        old_user = self.current_user_id
        self.set_current_user(user_id)
        try:
            yield
        finally:
            if old_user:
                self.set_current_user(old_user)
            else:
                self.clear_current_user()

    def log_info(self, message: str, **kwargs):
        """Log d'information avec contexte utilisateur"""
        try:
            if self.current_user_id:
                kwargs["user_id"] = self.current_user_id
            self.logger.info(message, **kwargs)
        except:
            print(f"INFO: {message} - {kwargs}")

    def log_error(self, message: str, **kwargs):
        """Log d'erreur avec contexte utilisateur"""
        try:
            if self.current_user_id:
                kwargs["user_id"] = self.current_user_id
            self.logger.error(message, **kwargs)
        except:
            print(f"ERROR: {message} - {kwargs}")

    def log_warning(self, message: str, **kwargs):
        """Log d'avertissement avec contexte utilisateur"""
        try:
            if self.current_user_id:
                kwargs["user_id"] = self.current_user_id
            self.logger.warning(message, **kwargs)
        except:
            print(f"WARNING: {message} - {kwargs}")

observability = ObservabilityManager()

def get_logger():
    """Retourne le logger structuré"""
    return observability.logger

def get_tracer():
    """Retourne le tracer OpenTelemetry"""
    return observability.tracer

def trace_function(name: str):
    """Décorateur pour tracer une fonction tout en conservant sa signature."""

    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if observability.tracer:
                    with observability.tracer.start_as_current_span(name) as span:
                        if observability.current_user_id:
                            span.set_attribute("user.id", observability.current_user_id)
                        span.set_attribute("function.name", func.__name__)

                        try:
                            result = await func(*args, **kwargs)
                            span.set_attribute("function.result", "success")
                            return result
                        except Exception as e:
                            span.set_attribute("function.result", "error")
                            span.set_attribute("error.message", str(e))
                            raise
                else:
                    return await func(*args, **kwargs)

            wrapper.__signature__ = inspect.signature(func)
            return wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                if observability.tracer:
                    with observability.tracer.start_as_current_span(name) as span:
                        if observability.current_user_id:
                            span.set_attribute("user.id", observability.current_user_id)
                        span.set_attribute("function.name", func.__name__)

                        try:
                            result = func(*args, **kwargs)
                            span.set_attribute("function.result", "success")
                            return result
                        except Exception as e:
                            span.set_attribute("function.result", "error")
                            span.set_attribute("error.message", str(e))
                            raise
                else:
                    return func(*args, **kwargs)

            wrapper.__signature__ = inspect.signature(func)
            return wrapper

    return decorator
