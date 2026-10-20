/**
 * The app's name and the document title of each page. Kept apart from `AppShell` so pages can
 * set their title without importing the shell that renders them.
 */
export namespace AppTitle {
  /**
   * The app's name: the app-bar heading and the suffix of every page's document title. It must
   * match the `<title>` of `resources/index.html` (shown until a page sets its own);
   * `AppTitle.test` fails when the two differ.
   */
  export const Name = "Code Search Local"

  /** Between a page's name and {@link Name}; changing it changes every browser-tab title. */
  export const Separator = " · "

  /**
   * The document title of one page.
   *
   * @param page the page's name (a project root, `Overview`, …).
   * @returns e.g. `Overview · Code Search Local`.
   */
  export function of(page: string): string {
    return `${page}${Separator}${Name}`
  }
}
