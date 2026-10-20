/**
 * Local ESLint plugin for the code-search-local workspace.
 *
 * `no-identity-arrow`: an `x => x` arrow IS lodash `identity`. A custom rule because
 * `no-restricted-syntax` (esquery) cannot assert body-name === param-name.
 */
export const CodeSearchLocalPlugin = {
  meta: { name: "csl-local" },
  rules: {
    "no-identity-arrow": {
      meta: {
        type: "problem",
        docs: { description: "Use lodash-es `identity` instead of an `x => x` arrow." },
        messages: {
          useLodashIdentity: "Use `identity` from lodash-es instead of an `x => x` arrow."
        },
        schema: []
      },
      create(context) {
        return {
          ArrowFunctionExpression(node) {
            const [param] = node.params
            if (
              node.params.length === 1 &&
              param.type === "Identifier" &&
              node.body.type === "Identifier" &&
              node.body.name === param.name
            ) {
              context.report({ node, messageId: "useLodashIdentity" })
            }
          }
        }
      }
    }
  }
}
