import { db } from '@/lib/db';
import { NextResponse } from 'next/server';

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;

    const existing = await db.userDiscount.findUnique({
      where: { id },
    });

    if (!existing) {
      return NextResponse.json({ error: 'Discount not found' }, { status: 404 });
    }

    await db.userDiscount.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'تخفیف کاربر حذف شد' });
  } catch (error) {
    console.error('Error deleting user discount:', error);
    return NextResponse.json({ error: 'Failed to delete user discount' }, { status: 500 });
  }
}
