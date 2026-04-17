import sys
import os
import asyncio
sys.path.append(os.getcwd())

from stream import stream_manager

async def test():
    try:
        print("Initialising stream...")
        gen = stream_manager.generate_frames()
        print("Getting first frame (this might take time to load models)...")
        frame = await gen.__anext__()
        print(f"Success! Got frame data of length {len(frame)}")
        print(f"Frame start: {frame[:20]}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
