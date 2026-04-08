export async function requestWithSessionRefresh(
  request: () => Promise<Response>,
  refreshSession: () => Promise<boolean>
) {
  const response = await request();
  if (response.status !== 401) {
    return response;
  }

  const refreshed = await refreshSession();
  if (!refreshed) {
    return response;
  }

  return await request();
}
