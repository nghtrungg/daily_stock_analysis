import { PortfolioPage } from '../../features/portfolio/portfolio-page';
import { PortfolioProvider } from '../../features/portfolio/portfolio-provider';
import { requireUser } from '../../lib/auth/require-user';

export default async function PortfolioRoute() {
  await requireUser();

  return <PortfolioProvider><PortfolioPage /></PortfolioProvider>;
}
