import { ActivityPage } from '../../features/activity/activity-page';
import { PortfolioProvider } from '../../features/portfolio/portfolio-provider';
import { requireUser } from '../../lib/auth/require-user';

export default async function ActivityRoute() {
  await requireUser();

  return <PortfolioProvider><ActivityPage /></PortfolioProvider>;
}
