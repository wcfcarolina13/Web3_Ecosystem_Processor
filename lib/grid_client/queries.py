"""
Parameterized GraphQL query templates for The Grid API.

All queries use $variables for safe parameterization (no string formatting).
"""

# Search profiles by name
SEARCH_PROFILES_QUERY = """
query SearchProfiles($search: String!, $limit: Int) {
  profileInfos(
    where: {
      _or: [
        { name: { _contains: $search } },
        { descriptionShort: { _contains: $search } }
      ]
    }
    limit: $limit
  ) {
    id
    name
    descriptionShort
    profileType { name }
    profileSector { name }
    profileStatus { name }
    root {
      slug
      urlMain
    }
  }
}
"""

# Search products by name
SEARCH_PRODUCTS_QUERY = """
query SearchProducts($search: String!, $limit: Int) {
  products(
    where: {
      _or: [
        { name: { _contains: $search } },
        { description: { _contains: $search } }
      ]
    }
    limit: $limit
  ) {
    id
    name
    description
    productType { name }
    productStatus { name }
    root {
      slug
      urlMain
    }
  }
}
"""

# Search assets by name or ticker
SEARCH_ASSETS_QUERY = """
query SearchAssets($search: String!, $limit: Int) {
  assets(
    where: {
      _or: [
        { name: { _contains: $search } },
        { ticker: { _contains: $search } }
      ]
    }
    limit: $limit
  ) {
    id
    name
    ticker
    assetType { name }
    assetStatus { name }
    root {
      slug
      urlMain
    }
  }
}
"""

# Search entities (legal structures)
SEARCH_ENTITIES_QUERY = """
query SearchEntities($search: String!, $limit: Int) {
  entities(
    where: {
      _or: [
        { name: { _contains: $search } },
        { tradeName: { _contains: $search } }
      ]
    }
    limit: $limit
  ) {
    id
    name
    tradeName
    entityType { name }
    country { name }
  }
}
"""

# Get detailed profile info by exact name
GET_PROFILE_DETAILS_QUERY = """
query GetProfileDetails($name: String!) {
  profileInfos(where: { name: { _eq: $name } }, limit: 1) {
    id
    name
    descriptionShort
    descriptionLong
    profileType { name }
    profileSector { name }
    profileStatus { name }
    root {
      id
      slug
      urlMain
      socials { url socialType { name } }
      urls { url urlType { name } }
    }
  }
}
"""

# Search by URL (match scraped projects to Grid)
SEARCH_BY_URL_QUERY = """
query SearchByURL($url: String!) {
  roots(where: { urlMain: { _contains: $url } }, limit: 5) {
    id
    slug
    urlMain
    profileInfos {
      id
      name
      profileType { name }
    }
    products {
      id
      name
      productType { name }
    }
  }
}
"""

# List all product types
GET_PRODUCT_TYPES_QUERY = """
query GetProductTypes {
  productTypes(limit: 200) {
    id
    name
  }
}
"""

# List all asset types
GET_ASSET_TYPES_QUERY = """
query GetAssetTypes {
  assetTypes(limit: 200) {
    id
    name
  }
}
"""

# Raw query for advanced use
INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    types {
      name
      kind
      fields {
        name
        type { name kind }
      }
    }
  }
}
"""
