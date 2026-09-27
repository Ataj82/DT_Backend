"""
Application composition root.

Constructs application-wide services and collaborators.
"""

from __future__ import annotations

from ..framework.assessment_framework import (
    AssessmentFramework,
)

from ..framework.framework_services import (
    FrameworkServices,
)

# ==========================================================
# Repositories
# ==========================================================

from ..repositories.memory.memory_knowledge_repository import (
    MemoryKnowledgeRepository,
)

from ..repositories.memory.memory_goal_repository import (
    MemoryGoalRepository,
)

from ..repositories.memory.memory_session_repository import (
    MemorySessionRepository,
)

# ==========================================================
# Unit Of Work
# ==========================================================

from ..unit_of_work.memory_unit_of_work import (
    MemoryUnitOfWork,
)

# ==========================================================
# Assessment
# ==========================================================

from ..assessment.coverage_engine import (
    CoverageEngine,
)

from ..assessment.difficulty import (
    AdaptiveDifficultyController,
)

from ..assessment.information_gain import (
    InformationGainPlanner,
)

from ..assessment.evidence_planner import (
    EvidencePlanner,
)

from ..assessment.outcome_manager import (
    OutcomeManager,
)

from ..assessment.progress_reasoner import (
    ProgressReasoner,
)

from ..assessment.engine import (
    AssessmentEngine,
)

from ..assessment.evaluation.evaluation_service import (
    EvaluationService,
)

from ..assessment.evaluation.answer_evaluator import (
    AnswerEvaluator,
)

from ..assessment.result_builder import (
    AssessmentResultBuilder,
)

from ..assessment.context_factory import (
    AssessmentContextFactory,
)

from ..abet.service import ABETService

from ..assessment.runtime_factory import (
    AssessmentRuntimeFactory,
)

# ==========================================================
# Interview
# ==========================================================

from ..interview.question_generator import (
    QuestionGenerator,
)

from ..interview.prompt_builder import (
    QuestionPromptBuilder,
)

from ..interview.knowledge_retriever import (
    KnowledgeRetriever,
)

# ==========================================================
# LLM
# ==========================================================

from ..llm.provider import (
    LLMProvider,
)

from ..configuration.llm_configuration import (
    LLMConfiguration,
)

# ==========================================================
# Application Services
# ==========================================================

from ..services.knowledge_service import (
    KnowledgeService,
)

from ..services.goal_service import (
    GoalService,
)

from ..services.interview_service import (
    InterviewService,
)

from ..services.assessment_service import (
    AssessmentService,
)
from ..multiuser.service import MultiUserService

# ==========================================================
# Reporting
# ==========================================================

from ..reports.metrics_service import (
    MetricsService,
)

from ..reports.report_service import (
    ReportService,
)

from ..reports.research_report_generator import (
    ResearchReportGenerator,
)

# ==========================================================
# Knowledge
# ==========================================================

from ..knowledge.processor import (
    KnowledgeProcessor,
)

from ..knowledge.provider import (
    KnowledgeProvider,
)


class FrameworkBuilder:
    """
    Application composition root.

    Production:

        FrameworkBuilder().build()

    Tests:

        FrameworkBuilder(
            configuration=...,
            llm=fake_llm,
        ).build()

    The builder owns dependency wiring only.
    """

    def __init__(
        self,
        *,
        configuration=None,
        llm=None,
    ) -> None:
        self.configuration = configuration
        self.llm = llm

    def build(
        self,
    ) -> AssessmentFramework:

        # ======================================================
        # Repositories
        # ======================================================

        knowledge_repository = (
            MemoryKnowledgeRepository()
        )

        goal_repository = (
            MemoryGoalRepository()
        )

        session_repository = (
            MemorySessionRepository()
        )

        # ======================================================
        # Unit Of Work
        # ======================================================

        unit_of_work = MemoryUnitOfWork(
            knowledge_repository=(
                knowledge_repository
            ),
            goal_repository=(
                goal_repository
            ),
            session_repository=(
                session_repository
            ),
        )

        # ======================================================
        # Knowledge Pipeline
        # ======================================================

        knowledge_provider = (
            KnowledgeProvider()
        )

        knowledge_processor = (
            KnowledgeProcessor()
        )

        # ======================================================
        # Assessment Algorithms
        # ======================================================

        coverage_engine = (
            CoverageEngine()
        )

        difficulty_controller = AdaptiveDifficultyController()

        information_gain_planner = (
            InformationGainPlanner()
        )

        evidence_planner = EvidencePlanner(
            information_gain_planner=(
                information_gain_planner
            ),
        )

        outcome_manager = OutcomeManager(
            coverage_engine=(
                coverage_engine
            ),
        )

        progress_reasoner = ProgressReasoner(
            coverage_engine=(
                coverage_engine
            ),
            evidence_planner=(
                evidence_planner
            ),
        )

        # ======================================================
        # LLM
        # ======================================================
        #
        # IMPORTANT:
        #
        # Build the LLM BEFORE constructing AnswerEvaluator.
        #
        # Otherwise:
        #
        #     AnswerEvaluator(llm=llm)
        #
        # references a local variable that does not yet exist.
        # ======================================================

        llm = self._build_llm()

        # ======================================================
        # Answer Evaluation
        # ======================================================
        #
        # P0:
        #
        # AnswerEvaluator is now the semantic evaluation boundary.
        #
        # It receives the same LLM instance used by the
        # question-generation pipeline.
        # ======================================================

        answer_evaluator = AnswerEvaluator(
            llm=llm,
        )

        evaluation_service = EvaluationService(
            evaluator=answer_evaluator,
            outcome_manager=outcome_manager,
            progress_reasoner=progress_reasoner,
            coverage_engine=coverage_engine,
        )

        assessment_engine = AssessmentEngine(
            evaluation_service=(
                evaluation_service
            ),
        )

        # ======================================================
        # Knowledge Retriever
        # ======================================================
        #
        # Current KnowledgeRetriever expects:
        #
        #     repository.retrieve(indicator)
        #
        # MemoryKnowledgeRepository exposes search().
        #
        # This adapter bridges that interface.
        #
        # Knowledge-base isolation remains a later task.
        # ======================================================

        class _KnowledgeRepositoryAdapter:
            """
            Compatibility adapter for KnowledgeRetriever.
            """

            def __init__(
                self,
                repository,
            ) -> None:
                self.repository = repository

            def retrieve(
                self,
                indicator,
            ) -> str:

                query = (
                    getattr(
                        indicator,
                        "description",
                        None,
                    )
                    or getattr(
                        indicator,
                        "name",
                        None,
                    )
                    or str(indicator)
                )

                parts: list[str] = []

                for knowledge_base in (
                    self.repository.list()
                ):
                    results = (
                        self.repository.search(
                            knowledge_id=(
                                knowledge_base.id
                            ),
                            query=query,
                            top_k=3,
                        )
                    )

                    for result in results:

                        if isinstance(
                            result,
                            dict,
                        ):
                            text = result.get(
                                "text"
                            )
                        else:
                            text = str(
                                result
                            )

                        if text:
                            parts.append(
                                text
                            )

                return (
                    "\n\n".join(parts)
                    or query
                )

        knowledge_retriever = KnowledgeRetriever(
            knowledge_repository=(
                _KnowledgeRepositoryAdapter(
                    knowledge_repository
                )
            ),
        )

        # ======================================================
        # Question Generation
        # ======================================================

        prompt_builder = (
            QuestionPromptBuilder()
        )

        question_generator = QuestionGenerator(
            llm=llm,
            knowledge_retriever=(
                knowledge_retriever
            ),
            prompt_builder=(
                prompt_builder
            ),
        )

        # ======================================================
        # Result Builder
        # ======================================================

        result_builder = (
            AssessmentResultBuilder()
        )

        # ======================================================
        # Runtime Factories
        # ======================================================

        abet_service = ABETService()

        context_factory = AssessmentContextFactory(
            coverage_engine=(
                coverage_engine
            ),
            evidence_planner=(
                evidence_planner
            ),
            progress_reasoner=(
                progress_reasoner
            ),
            question_generator=(
                question_generator
            ),
            result_builder=(
                result_builder
            ),
            abet_service=abet_service,
        )

        runtime_factory = AssessmentRuntimeFactory(
            context_factory=(
                context_factory
            ),
            result_builder=(
                result_builder
            ),
            evaluation_service=(
                evaluation_service
            ),
            difficulty_controller=(
                difficulty_controller
            ),
            abet_service=abet_service,
        )

        # ======================================================
        # Application Services
        # ======================================================

        knowledge_service = KnowledgeService(
            provider=knowledge_provider,
            processor=knowledge_processor,
            uow=unit_of_work,
        )

        goal_service = GoalService(
            uow=unit_of_work,
        )

        interview_service = InterviewService(
            runtime_factory=(
                runtime_factory
            ),
            uow=unit_of_work,
        )

        assessment_service = AssessmentService(
            runtime_factory=(
                runtime_factory
            ),
            uow=unit_of_work,
        )

        # ======================================================
        # Reporting
        # ======================================================

        metrics_service = (
            MetricsService()
        )

        report_service = ReportService(
            generator=(
                ResearchReportGenerator()
            ),
            metrics_service=(
                metrics_service
            ),
        )

        # ======================================================
        # Multi-user assignment layer
        # ======================================================
        # This layer sits above InterviewService and never participates in
        # question generation, evaluation, scoring, navigation, or mastery.
        multi_user_service = MultiUserService(
            interview_service=interview_service,
            knowledge_service=knowledge_service,
            goal_service=goal_service,
        )

        # ======================================================
        # Framework
        # ======================================================

        services = FrameworkServices(
            knowledge_service=(
                knowledge_service
            ),
            goal_service=(
                goal_service
            ),
            interview_service=(
                interview_service
            ),
            assessment_service=(
                assessment_service
            ),
            report_service=(
                report_service
            ),
            abet_service=abet_service,
            multi_user_service=multi_user_service,
        )

        return AssessmentFramework(
            services=services
        )

    # ==========================================================
    # LLM Construction
    # ==========================================================

    def _build_llm(self):
        """
        Resolve the LLM dependency.

        Priority:

        1. Explicitly injected provider.
        2. Configuration object's LLM configuration.
        3. Environment-backed LLMConfiguration.
        """

        if self.llm is not None:
            return self.llm

        llm_configuration = getattr(
            self.configuration,
            "llm",
            None,
        )

        if llm_configuration is None:
            llm_configuration = (
                LLMConfiguration.from_env()
            )

        return LLMProvider(
            configuration=llm_configuration,
        )