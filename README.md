### 🌟 Key Enhancements & Architecture Updates

* **Modular Filter Pipeline (Plug-and-Play)**: Pixel-level manipulation (such as CLAHE or Tone Mapping) has been completely decoupled from the file-handling system and isolated into discrete, modular routines. This major structural change paves the way for adding multiple image processing modes (e.g., custom AI filters, sharpening, or grayscale conversion) in future updates without breaking core operations.
* **MVVM Multi-Threading with Dynamic I/O Scaling**: Built using the `ThreadPoolExecutor` architecture. The tool dynamically monitors storage hardware benchmarks using system partitions analysis. 
  * *Internal SSD/HDD Target*: Spawns up to 8 concurrent worker threads.
  * *Removable USB Flash Drives Target*: Automatically throttles down to single-thread sequential processing to prevent heavy hardware queuing constraints.
* **Persistent Settings (Zero-Footprint File Structure)**: Automatically intercepts application close lifecycles to back up session paths natively inside the host profile cache folder, preventing local workspace folder pollution.
* **Selective Purge Protection**: Embedded format validation filters on the directory cleaning toolkit to ensure absolute safety against accidental data losses.