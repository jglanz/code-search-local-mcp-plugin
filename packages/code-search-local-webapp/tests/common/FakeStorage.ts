/** An in-memory `Storage` (the token store's `sessionStorage` stand-in, usable in node tests). */
export class FakeStorage implements Storage {
  private readonly items = new Map<string, string>()

  /** Entries stored. */
  get length(): number {
    return this.items.size
  }

  /**
   * Create a storage, optionally holding entries.
   *
   * @param entries initial key → value pairs.
   * @returns the storage.
   */
  static create(entries: Record<string, string> = {}): FakeStorage {
    const storage = new FakeStorage()
    Object.entries(entries).forEach(([key, value]) =>
      storage.setItem(key, value)
    )
    return storage
  }

  /** Remove every entry. */
  clear(): void {
    this.items.clear()
  }

  /**
   * @param key the key.
   * @returns its value, or null when absent (the `Storage` contract).
   */
  getItem(key: string): string {
    return this.items.has(key) ? this.items.get(key) : null
  }

  /**
   * @param index the position.
   * @returns the key at it, or null (the `Storage` contract).
   */
  key(index: number): string {
    const keys = [...this.items.keys()]
    return index < keys.length ? keys[index] : null
  }

  /**
   * @param key the key to remove.
   */
  removeItem(key: string): void {
    this.items.delete(key)
  }

  /**
   * @param key the key.
   * @param value its value.
   */
  setItem(key: string, value: string): void {
    this.items.set(key, String(value))
  }
}
