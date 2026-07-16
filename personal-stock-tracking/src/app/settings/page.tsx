import { Settings } from 'lucide-react';
import { UtilityPage } from '../../components/utility-page';
import { SignOutButton } from '../../features/auth/sign-out-button';
import { requireUser } from '../../lib/auth/require-user';

export default async function SettingsPage() {
  await requireUser();

  return (
    <UtilityPage
      activePath="/settings"
      eyebrow="Tùy chọn ứng dụng"
      title="Cài đặt"
      description="Dữ liệu được bảo vệ bằng phiên tài khoản và chính sách bảo mật theo từng dòng. Giá thị trường sẽ được hiển thị là chưa có cho đến khi kết nối nguồn giá đáng tin cậy."
      marker={<Settings size={28} strokeWidth={1.5} />}
      emptyTitle="Không gian danh mục an toàn"
      emptyCopy="Sổ giao dịch và danh sách theo dõi của bạn được lưu riêng tư. Thời điểm cập nhật giá sẽ được bổ sung trong các bước tiếp theo."
      action={<SignOutButton />}
    />
  );
}
