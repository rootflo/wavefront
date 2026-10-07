"""Wire all floware DI containers into controller/service packages."""

from floware.di.containers import (
    agents_container,
    api_services_container,
    application_container,
    auth_container,
    chatbots_container,
    common_container,
    db_repo_container,
    gold_container,
    guardrails_container,
    knowledge_base_container,
    llm_inference_config_container,
    plugins_container,
    product_analysis_container,
    tools_container,
    user_module_container,
    voice_agents_container,
)


def wire_containers() -> None:
    # Controllers are covered via packages=; no modules= to avoid a cycle with
    # server importing this module.
    application_container.wire(packages=['floware.controllers'])

    db_repo_container.wire(
        packages=[
            'product_analysis_module.product_analysis_service',
        ],
    )

    product_analysis_container.wire(
        packages=['product_analysis_module.controllers'],
    )

    user_module_container.wire(
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

    auth_container.wire(
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
            'user_management_module.controllers',
            'plugins_module.services',
            'plugins_module.controllers',
            'llm_inference_config_module.controllers',
        ],
    )

    gold_container.wire(
        packages=['gold_module.controllers'],
    )

    common_packages = [
        'auth_module.controllers',
        'user_management_module.controllers',
        'user_management_module.authorization',
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
    if guardrails_container is not None:
        common_packages.append('guardrails_module.controllers')
    common_container.wire(packages=common_packages)

    knowledge_base_container.wire(
        packages=[
            'knowledge_base_module.controllers',
            'auth_module.controllers',
        ],
    )

    plugins_container.wire(
        packages=[
            'plugins_module.controllers',
            'plugins_module.services',
            'floware.controllers',
            'user_management_module.controllers',
            'user_management_module.authorization',
            'tools_module.datasources',
        ],
    )

    agents_container.wire(
        packages=[
            'agents_module.controllers',
            'agents_module.services',
        ],
    )

    llm_inference_config_container.wire(
        packages=[
            'llm_inference_config_module.controllers',
            'agents_module.controllers',
            'knowledge_base_module.controllers',
        ],
    )

    if guardrails_container is not None:
        guardrails_container.wire(
            packages=[
                'guardrails_module.controllers',
                # Agent inference resolves policy when constructing a guarded LLM.
                'agents_module.controllers',
            ],
        )

    tools_container.wire(
        packages=[
            'tools_module.controllers',
        ],
    )

    api_services_container.wire(
        packages=['api_services_module.core'],
    )

    voice_agents_container.wire(
        packages=[
            'voice_agents_module.controllers',
            'voice_agents_module.services',
        ],
    )

    chatbots_container.wire(
        packages=[
            'chatbots_module.controllers',
        ],
    )
