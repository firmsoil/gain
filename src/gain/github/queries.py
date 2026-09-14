PR_BACKFILL_QUERY = r"""
query PullRequestsForRepository(
  $owner: String!,
  $name: String!,
  $first: Int!,
  $after: String,
  $since: DateTime!,
  $until: DateTime!
) {
  repository(owner: $owner, name: $name) {
    id
    nameWithOwner
    pullRequests(first: $first, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        id
        number
        author {
          __typename
          login
        }
        createdAt
        closedAt
        mergedAt
        state
        isDraft
        additions
        deletions
        changedFiles
        reviewDecision
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

# The initial query orders ascending and then filters client-side because a repository
# connection does not expose a generic createdAt filter. The API response remains the
# source of truth; filtering is explicit and covered by tests.
