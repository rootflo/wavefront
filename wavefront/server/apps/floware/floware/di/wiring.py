"""Wire all floware DI containers into controller/service packages.

``Provide[SomeContainer.x]`` markers match the child container class, so each
child is wired itself. Wiring only the application container resolves ``Provide[ApplicationContainer.x]``.
"""

from floware.di import application_container


def wire_containers() -> None:
    # Controllers are covered via packages=; no modules= to avoid a cycle with
    # server importing this module.
    application_container.wire(packages=['floware.controllers'])

    application_container.db.wire(
        packages=[
            'product_analysis_module.product_analysis_service',
        ],
    )

    application_container.product_analysis.wire(
        packages=['product_analysis_module.controllers'],
    )

    application_container.user.wire(
        packages=[
            'auth_module.controllers',
            'plugins_module.controllers',
            'user_management_module.controllers',
            'user_management_module.authorization',
            # Helpers in utils (check_is_admin and its callers) resolve container
            # providers themselves, so the package needs wiring too — otherwise only
            # the copies imported into wired controller modules get patched.
            'user_management_module.utils',
            'plugins_module.controllers',
        ],
    )

    application_container.auth.wire(
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
            'user_management_module.controllers',
            'plugins_module.services',
            'plugins_module.controllers',
            'llm_inference_config_module.controllers',
        ],
    )

    application_container.gold.wire(
        packages=['gold_module.controllers'],
    )

    common_packages = [
        'auth_module.controllers',
        'user_management_module.controllers',
        'user_management_module.authorization',
        'user_management_module.utils',
        'chatbots_module.controllers',
        'floware.controllers',
        'knowledge_base_module.controllers',
        'gold_module.controllers',
        'plugins_module.controllers',
        'plugins_module.services',
        'product_analysis_module.controllers',
        'agents_module.controllers',
        'agents_module.services',
        'llm_inference_config_module.controllers',
        'tools_module.controllers',
        'voice_agents_module.controllers',
    ]
    guardrails = application_container.guardrails()
    if guardrails is not None:
        common_packages.append('guardrails_module.controllers')
    application_container.common.wire(packages=common_packages)

    application_container.knowledge_base.wire(
        packages=[
            'knowledge_base_module.controllers',
            'auth_module.controllers',
        ],
    )

    application_container.plugins.wire(
        packages=[
            'plugins_module.controllers',
            'plugins_module.services',
            'floware.controllers',
            'user_management_module.controllers',
            'user_management_module.authorization',
            'tools_module.datasources',
        ],
    )

    application_container.agents.wire(
        packages=[
            'agents_module.controllers',
            'agents_module.services',
        ],
    )

    application_container.llm_inference_config.wire(
        packages=[
            'llm_inference_config_module.controllers',
            'agents_module.controllers',
            'knowledge_base_module.controllers',
        ],
    )

    if guardrails is not None:
        guardrails.wire(
            packages=[
                'guardrails_module.controllers',
                # Agent inference resolves policy when constructing a guarded LLM.
                'agents_module.controllers',
            ],
        )

    application_container.tools.wire(
        packages=[
            'tools_module.controllers',
        ],
    )

    application_container.api_services.wire(
        modules=['api_services_module.api_services_container'],
        packages=[
            'api_services_module.core',
            'api_services_module.execution',
        ],
    )

    application_container.voice_agents.wire(
        packages=[
            'voice_agents_module.controllers',
            'voice_agents_module.services',
        ],
    )

    application_container.chatbots.wire(
        packages=[
            'chatbots_module.controllers',
        ],
    )
