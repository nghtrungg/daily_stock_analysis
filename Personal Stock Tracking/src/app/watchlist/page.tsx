import { WatchlistPage } from '../../features/watchlist/watchlist-page';
import { PortfolioProvider } from '../../features/portfolio/portfolio-provider';
import { requireUser } from '../../lib/auth/require-user';

export default async function WatchlistRoute() {
  await requireUser();

  return <PortfolioProvider><WatchlistPage /></PortfolioProvider>;
}
