"""
Simple demonstration of ReflectionRouter for A -> B -> A -> C patterns.

This shows the minimal code needed to implement a main -> critic -> main -> final
reflection pattern using the new ReflectionRouter.
"""

import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemory
from flo_ai.models.agent import Agent
from flo_ai.llm import OpenAI
from flo_ai.arium.llm_router import create_main_critic_reflection_router


async def simple_reflection_demo():
    """Minimal example of A -> B -> A -> C reflection pattern"""
    print('🚀 Simple ReflectionRouter Demo: A → B → A → C Pattern')
    print('=' * 60)

    # Create LLM (use dummy key for demo)
    llm = OpenAI(model='gpt-4o-mini')

    # Create agents
    main_agent = Agent(
        name='main_agent',
        system_prompt='You are the main agent. Analyze tasks and create solutions.',
        llm=llm,
    )

    critic = Agent(
        name='critic',
        system_prompt='You are a critic. Provide constructive feedback to improve work.',
        llm=llm,
    )

    final_agent = Agent(
        name='final_agent',
        system_prompt='You are the final agent. Polish and finalize the work.',
        llm=llm,
    )

    # Create reflection router for A -> B -> A -> C pattern
    reflection_router = create_main_critic_reflection_router(
        main_agent='main_agent',
        critic_agent='critic',
        final_agent='final_agent',
        allow_early_exit=False,  # Strict reflection
        llm=llm,
    )

    # Build workflow
    builder = (
        AriumBuilder()
        .with_memory(MessageMemory())
        .add_agents([main_agent, critic, final_agent])
        .start_with(main_agent)
        .add_edge(main_agent, [critic, final_agent], reflection_router)
        .add_edge(critic, [main_agent, final_agent], reflection_router)
        .end_with(final_agent)
    )

    # Build the Arium
    arium = builder.build()

    print('✅ Workflow created successfully!')
    print('📋 Reflection Pattern: main_agent → critic → main_agent → final_agent')
    print('🎯 Router will automatically follow this sequence')

    # Demo input
    print('\n📝 Example input: "Create a project plan for a mobile app"')
    print('💡 The reflection router will:')
    print('   Step 1: Route to critic (for feedback/reflection)')
    print('   Step 2: Return to main_agent (to incorporate feedback)')
    print('   Step 3: Route to final_agent (for final polish)')

    return arium


async def programmatic_reflection_example():
    """Show how to create reflection router programmatically"""
    print('\n\n🔧 Programmatic ReflectionRouter Creation')
    print('=' * 50)

    from flo_ai.arium.llm_router import create_llm_router

    # Method 1: Using the convenience function
    create_main_critic_reflection_router(
        main_agent='writer',
        critic_agent='reviewer',
        final_agent='editor',
        llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )
    print('✅ Method 1: Convenience function create_main_critic_reflection_router()')

    # Method 2: Using the factory function directly
    create_llm_router(
        'reflection',
        flow_pattern=['analyst', 'validator', 'analyst', 'presenter'],
        allow_early_exit=True,
        llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )
    print('✅ Method 2: Factory function create_llm_router(type="reflection")')

    # Method 3: Creating ReflectionRouter directly
    from flo_ai.arium.llm_router import ReflectionRouter

    ReflectionRouter(
        flow_pattern=['main', 'critic', 'main', 'final'],
        allow_early_exit=False,
        llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )
    print('✅ Method 3: Direct ReflectionRouter instantiation')

    print('\n🎯 All methods create the same A→B→A→C reflection pattern!')


def show_minimal_yaml():
    """Show the minimal YAML needed"""
    print('\n\n📄 Minimal YAML Configuration')
    print('=' * 35)

    yaml_example = """
# Minimal ReflectionRouter YAML
arium:
  agents:
    - name: main_agent
      job: "Main agent job"
      model: {provider: openai, name: gpt-4o-mini}
    - name: critic
      job: "Critic job" 
      model: {provider: openai, name: gpt-4o-mini}
    - name: final_agent
      job: "Final agent job"
      model: {provider: openai, name: gpt-4o-mini}

  routers:
    - name: reflection_router
      type: reflection
      flow_pattern: [main_agent, critic, main_agent, final_agent]

  workflow:
    start: main_agent
    edges:
      - from: main_agent
        to: [critic, final_agent]
        router: reflection_router
      - from: critic  
        to: [main_agent, final_agent]
        router: reflection_router
      - from: final_agent
        to: [end]
    end: [final_agent]
"""
    print(yaml_example)


async def main():
    """Run the simple demo"""
    print('🌟 Simple ReflectionRouter Demo')
    print('=' * 35)
    print('Demonstrating A → B → A → C reflection pattern with minimal setup\n')

    # Show different creation methods
    await programmatic_reflection_example()

    # Show minimal YAML
    show_minimal_yaml()

    # Create simple reflection workflow
    arium = await simple_reflection_demo()

    result = await arium.run(
        inputs=['Write a comprehensive guide on sustainable urban planning']
    )

    print('\n\n🎉 Demo completed!')
    print('Key takeaways:')
    print('✅ ReflectionRouter makes A→B→A→C patterns trivial to implement')
    print('✅ Works with both YAML and programmatic configuration')
    print('✅ Automatically tracks progress and prevents infinite loops')
    print('✅ Provides intelligent routing based on execution context')

    print(result)


if __name__ == '__main__':
    asyncio.run(main())
