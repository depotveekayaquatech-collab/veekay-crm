import { BrandLogo } from "@/components/ui/BrandLogo";
import { PasswordForm } from "@/features/auth/PasswordForm";
import { useAuth } from "@/features/auth/useAuth";

/** Shown instead of the app while the signed-in person still has a temporary / admin-set password. */
export function ForcedPasswordChange() {
  const { user, logout } = useAuth();
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-subtle px-4 py-10">
      <div className="w-full max-w-md animate-slide-up">
        <div className="mb-6 flex items-center gap-2.5">
          <BrandLogo height={40} />
          <span className="text-base font-bold text-heading">Veekay Aquatech</span>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface p-6 shadow-card">
          <h1 className="text-xl font-bold text-heading">Choose your own password</h1>
          <p className="mt-1.5 text-sm text-gray-500">
            Hi {user?.fullName?.split(" ")[0] ?? "there"} — you signed in with a temporary password. Set a new one to continue.
          </p>
          <div className="mt-5">
            <PasswordForm forced />
          </div>
        </div>
        <button onClick={() => void logout()} className="mt-4 text-sm font-medium text-gray-500 hover:text-gray-800">
          Sign out instead
        </button>
      </div>
    </div>
  );
}
