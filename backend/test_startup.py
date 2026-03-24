import asyncio
from main import lifespan, app

async def test():
    try:
        async with lifespan(app):
            print("Lifespan started successfully!")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())
